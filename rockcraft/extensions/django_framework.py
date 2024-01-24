# -*- Mode:Python; indent-tabs-mode:nil; tab-width:4 -*-
#
# Copyright 2023 Canonical Ltd.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""An experimental extension for the Django framework."""
import ast
import copy
import fnmatch
import posixpath
import re
import textwrap
from typing import Any, Dict, Optional, Tuple

from overrides import override

from ..errors import ExtensionError
from ._utils import _apply_extension_property
from .extension import Extension


class DjangoFramework(Extension):
    """An extension for constructing Python applications based on the Django framework."""

    @staticmethod
    @override
    def get_supported_bases() -> Tuple[str, ...]:
        """Return supported bases."""
        return "bare", "ubuntu:20.04", "ubuntu:22.04"

    @staticmethod
    @override
    def is_experimental(base: Optional[str]) -> bool:
        """Check if the extension is in an experimental state."""
        return True

    @override
    def get_root_snippet(self) -> Dict[str, Any]:
        """Fill in some default root components for Django.

        Default values:
          - run_user: _daemon_
          - build-base: ubuntu:22.04 (only if user specify bare without a build-base)
          - platform: amd64
        """
        snippet: Dict[str, Any] = {}
        if "run_user" not in self.yaml_data:
            snippet["run_user"] = "_daemon_"
        if (
            "build-base" not in self.yaml_data
            and self.yaml_data.get("base", "bare") == "bare"
        ):
            snippet["build-base"] = "ubuntu:22.04"
        if "platforms" not in self.yaml_data:
            snippet["platforms"] = {"amd64": {}}
        current_parts = copy.deepcopy(self.yaml_data.get("parts", {}))
        current_parts.update(self._gen_new_parts())
        snippet["parts"] = current_parts
        snippet["services"] = self._gen_services()
        return snippet

    def _get_wsgi_path(self) -> str:
        """Get the django application WSGI path."""
        install_app_part_name = "django-framework/install-app"
        search = [
            f[len("django/app/") :]
            for f in self.yaml_data.get("parts", {})
            .get(install_app_part_name, {})
            .get("prime", [])
        ]

        wsgi_files = []
        for search_file in search:
            file = self.project_root / search_file
            if file.is_file() and file.name == "wsgi.py":
                wsgi_files.append(file)
            if file.is_dir():
                wsgi_files.extend(file.glob("**/wsgi.py"))
        if not wsgi_files:
            raise ExtensionError(
                "cannot detect Django WSGI path, no wsgi.py file found in the project"
            )
        if len(wsgi_files) >= 2:
            raise ExtensionError(
                f"cannot decide Django WSGI path, multiple wsgi.py file {wsgi_files} found in the project"
            )
        wsgi_file = wsgi_files[0]
        wsgi_path = (
            str(wsgi_file.relative_to(self.project_root)).replace("/", ".")[:-3]
            + ":application"
        )
        tree = ast.parse(wsgi_files[0].read_text(encoding="utf-8"))
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "application":
                        return wsgi_path
            if isinstance(node, ast.ImportFrom):
                for name in node.names:
                    if (name.asname is not None and name.asname == "application") or (
                        name.asname is None and name.name == "application"
                    ):
                        return wsgi_path
        raise ExtensionError(
            f"cannot detect Django WSGI path, no variable named `application` in {wsgi_file}"
        )

    def _gen_services(self):
        """Return the services snipped to be applied to the rockcraft file."""
        wsgi_path = self._get_wsgi_path()
        services = {
            "django": {
                "override": "merge",
                "startup": "enabled",
                "command": f"/bin/python3 -m gunicorn -c /django/gunicorn.conf.py {wsgi_path}",
                "after": ["statsd-exporter"],
                "user": "_daemon_",
            },
            "statsd-exporter": {
                "override": "merge",
                "summary": "statsd exporter service",
                "user": "_daemon_",
                "command": "/bin/statsd_exporter --statsd.mapping-config=/statsd-mapping.conf",
                "startup": "enabled",
            },
        }
        existing_services = copy.deepcopy(self.yaml_data.get("services", {}))
        for existing_service_name, existing_service in existing_services.items():
            if existing_service_name in services:
                services[existing_service_name].update(existing_service)
            else:
                services[existing_service_name] = existing_service
        return services

    @override
    def get_part_snippet(self) -> Dict[str, Any]:
        """Return the part snippet to apply to existing parts."""
        return {}

    def _merge_part(self, base_part: dict, new_part: dict) -> dict:
        """Merge two part definitions by the extension part merging rule."""
        result = {}
        properties = set(base_part.keys()).union(set(new_part.keys()))
        for property_name in properties:
            if property_name in base_part and property_name not in new_part:
                result[property_name] = base_part[property_name]
            elif property_name not in base_part and property_name in new_part:
                result[property_name] = new_part[property_name]
            else:
                result[property_name] = _apply_extension_property(
                    base_part[property_name], new_part[property_name]
                )
        return result

    def _merge_existing_part(self, part_name: str, part_def: dict) -> dict:
        """Merge the new part with the existing part in the current rockcraft.yaml."""
        existing_part = self.yaml_data.get("parts", {}).get(part_name, {})
        return self._merge_part(existing_part, part_def)

    def _gen_new_parts(self) -> Dict[str, Any]:
        """Generate new parts for the django extension.

        Parts added:
            - django/dependencies: install Python dependencies
            - django/install-app: copy the django project into the OCI image
            - django/statsd-exporter: build and install the statsd_exporter
            - django/statsd-mapping: create the statsd_exporter mapping configuration file
        """
        if not (self.project_root / "requirements.txt").exists():
            raise ExtensionError(
                "missing requirements.txt file, "
                "django extension requires this file with django specified as a dependency"
            )
        source_files = [f.name for f in sorted(self.project_root.iterdir())]
        renaming_map = {
            f: posixpath.join("django/app", f)
            for f in source_files
            if not any(
                fnmatch.fnmatch(f, p)
                for p in ("node_modules", ".git", ".yarn", "*.rock")
            )
        }
        install_app_part_name = "django-framework/install-app"
        user_prime = (
            self.yaml_data.get("parts", {})
            .get(install_app_part_name, {})
            .get("prime", [])
        )
        if not user_prime:
            raise ExtensionError(
                "django extension requires prime in the django/install-app part"
            )
        if not all(re.match("-? *django/app", p) for p in user_prime):
            raise ExtensionError(
                "django extension required prime entry in the django/install-app part"
                "to start with django/app"
            )

        # Users are required to compile any static assets prior to executing the
        # rockcraft pack command, so assets can be included in the final OCI image.
        install_app_part = {
            "plugin": "dump",
            "source": ".",
            "organize": renaming_map,
            "stage": list(renaming_map.values()),
        }
        parts = {
            install_app_part_name: install_app_part,
            "django-framework/gunicorn-config": {
                "plugin": "nil",
                "override-build": textwrap.dedent(
                    """\
                    #!/bin/bash
                    craftctl default
                    mkdir -p $CRAFT_PART_INSTALL/django/
                    GUNICORN_CONFIG=$CRAFT_PART_INSTALL/django/gunicorn.conf.py
                    echo 'bind = ["0.0.0.0:8000"]' > $GUNICORN_CONFIG
                    echo 'chdir = "/django/app"' >> $GUNICORN_CONFIG
                    echo 'statsd_host = "localhost:9125"' >> $GUNICORN_CONFIG"""
                ),
            },
            "django-framework/dependencies": {
                "plugin": "python",
                "stage-packages": ["python3-venv"],
                "source": ".",
                "python-packages": ["gunicorn"],
                "python-requirements": ["requirements.txt"],
            },
            "django-framework/statsd-exporter": {
                "plugin": "go",
                "build-snaps": ["go"],
                "source": "https://github.com/prometheus/statsd_exporter.git",
                "source-tag": "v0.26.0",
            },
            "django-framework/statsd-mapping": {
                "plugin": "nil",
                "override-build": textwrap.dedent(
                    """\
                    #!/bin/bash
                    craftctl default
                    STATSD_MAPPING_FILE=$CRAFT_PART_INSTALL/statsd-mapping.conf
                    echo 'mappings:' > $STATSD_MAPPING_FILE
                    echo '  - match: gunicorn.request.status.*' >> $STATSD_MAPPING_FILE
                    echo '    name: django_response_code' >> $STATSD_MAPPING_FILE
                    echo '    labels:' >> $STATSD_MAPPING_FILE
                    echo '      status: $1' >> $STATSD_MAPPING_FILE
                    echo '  - match: gunicorn.requests' >> $STATSD_MAPPING_FILE
                    echo '    name: django_requests' >> $STATSD_MAPPING_FILE
                    echo '  - match: gunicorn.request.duration' >> $STATSD_MAPPING_FILE
                    echo '    name: django_request_duration' >> $STATSD_MAPPING_FILE"""
                ),
            },
        }
        snippet = {
            name: self._merge_existing_part(name, part) for name, part in parts.items()
        }
        return snippet

    @override
    def get_parts_snippet(self) -> Dict[str, Any]:
        """Return the parts to add to parts."""
        return {}
