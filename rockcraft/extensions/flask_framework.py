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

"""An experimental extension for the Gunicorn based Python WSGI application extensions."""
import abc
import ast
import fnmatch
import os.path
import posixpath
import re
import textwrap
from typing import Any, Dict, List, Tuple

from overrides import override

from ..errors import ExtensionError
from .extension import Extension


class _GunicornBase(Extension):
    """An extension base class for Python WSGI framework extensions."""

    @staticmethod
    @override
    def get_supported_bases() -> Tuple[str, ...]:
        """Return supported bases."""
        return "bare", "ubuntu@20.04", "ubuntu@22.04", "ubuntu:20.04", "ubuntu:22.04"

    @staticmethod
    @override
    def is_experimental(base: str | None) -> bool:
        """Check if the extension is in an experimental state."""
        return True

    @property
    @abc.abstractmethod
    def wsgi_path(self) -> str:
        """Return the wsgi path of the wsgi application."""

    @property
    @abc.abstractmethod
    def framework(self) -> str:
        """Return the wsgi framework name, e.g. flask, django."""

    @property
    @abc.abstractmethod
    def app_prime(self) -> List[str]:
        """Return the prime list for the wsgi application project."""

    @abc.abstractmethod
    def check_project(self):
        """Ensure this extension can apply to the current rockcraft project."""

    def _gen_parts(self):
        """Generate the parts associated with this extension."""
        source_files = [f.name for f in sorted(self.project_root.iterdir())]
        # if prime is not in exclude mode, use it to generate the stage and organize
        if self.app_prime and self.app_prime[0] and self.app_prime[0][0] != "-":
            renaming_map = {
                os.path.relpath(file, f"{self.framework}/app"): file
                for file in self.app_prime
            }
        else:
            renaming_map = {
                f: posixpath.join(f"{self.framework}/app", f)
                for f in source_files
                if not any(
                    fnmatch.fnmatch(f, p)
                    for p in ("node_modules", ".git", ".yarn", "*.rock")
                )
            }
        parts: Dict[str, Any] = {
            f"{self.framework}-framework/dependencies": {
                "plugin": "python",
                "stage-packages": ["python3-venv"],
                "source": ".",
                "python-packages": ["gunicorn"],
                "python-requirements": ["requirements.txt"],
            },
            f"{self.framework}-framework/install-app": {
                "plugin": "dump",
                "source": ".",
                "organize": renaming_map,
                "stage": list(renaming_map.values()),
                "prime": self.app_prime,
            },
            f"{self.framework}-framework/gunicorn-config": {
                "plugin": "nil",
                "override-build": textwrap.dedent(
                    f"""\
                    #!/bin/bash
                    craftctl default
                    mkdir -p $CRAFT_PART_INSTALL/{self.framework}/
                    GUNICORN_CONFIG=$CRAFT_PART_INSTALL/{self.framework}/gunicorn.conf.py
                    echo 'bind = ["0.0.0.0:8000"]' > $GUNICORN_CONFIG
                    echo 'chdir = "/{self.framework}/app"' >> $GUNICORN_CONFIG
                    """
                ),
            },
        }
        if self.yaml_data["base"] == "bare":
            parts[f"{self.framework}-framework/misc"] = {
                "plugin": "nil",
                "source": ".",
                "override-build": "mkdir -m 777 ${CRAFT_PART_INSTALL}/tmp",
                "stage-packages": [
                    "bash_bins",
                    "coreutils_bins",
                    "ca-certificates_data",
                ],
            }
        else:
            parts[f"{self.framework}-framework/misc"] = {
                "plugin": "nil",
                "source": ".",
                "stage-packages": ["ca-certificates_data"],
            }
        return parts

    @override
    def get_root_snippet(self) -> Dict[str, Any]:
        """Fill in some default root components.

        Default values:
          - run_user: _daemon_
          - build-base: ubuntu:22.04 (only if user specify bare without a build-base)
          - platform: amd64
          - services: a service to run the Gunicorn server
          - parts: see _GunicornBase._gen_parts
        """
        self.check_project()
        snippet: Dict[str, Any] = {
            "run_user": "_daemon_",
            "services": {
                self.framework: {
                    "override": "replace",
                    "startup": "enabled",
                    "command": f"/bin/python3 -m gunicorn -c /{self.framework}/gunicorn.conf.py {self.wsgi_path}",
                    "user": "_daemon_",
                }
            },
        }
        if (
            "build-base" not in self.yaml_data
            and self.yaml_data.get("base", "bare") == "bare"
        ):
            snippet["build-base"] = "ubuntu@22.04"
        if "platforms" not in self.yaml_data:
            snippet["platforms"] = {"amd64": {}}
        snippet["parts"] = self._gen_parts()
        return snippet

    @override
    def get_part_snippet(self) -> Dict[str, Any]:
        """Return the part snippet to apply to existing parts."""
        return {}

    @override
    def get_parts_snippet(self) -> Dict[str, Any]:
        """Return the parts to add to parts."""
        return {}


class FlaskFramework(_GunicornBase):
    """An extension for constructing Python applications based on the Flask framework."""

    @property
    @override
    def wsgi_path(self) -> str:
        """Return the wsgi path of the wsgi application."""
        return "app:app"

    @property
    @override
    def framework(self) -> str:
        """Return the wsgi framework name, e.g. flask, django."""
        return "flask"

    @property
    @override
    def app_prime(self):
        """Return the prime list for the Flask project."""
        user_prime = (
            self.yaml_data.get("parts", {})
            .get("flask-framework/install-app", {})
            .get("prime", [])
        )
        if not all(re.match("-? *flask/app", p) for p in user_prime):
            raise ExtensionError(
                "flask-framework extension required prime entry in the "
                "flask-framework/install-app part to start with flask/app"
            )
        if not user_prime:
            user_prime = [
                f"flask/app/{f}"
                for f in (
                    "app",
                    "app.py",
                    "migrate",
                    "migrate.sh",
                    "migrate.py",
                    "static",
                    "templates",
                )
                if (self.project_root / f).exists()
            ]
        return user_prime

    def _check_wsgi_path(self):
        """Ensure the extension can infer the WSGI path of the Flask application."""
        app_file = self.project_root / "app.py"
        if not app_file.exists():
            raise ExtensionError(
                "flask application can not be imported from app:app, "
                "no app.py file found in the project root"
            )
        tree = ast.parse(app_file.read_text(encoding="utf-8"))
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "app":
                        return
            if isinstance(node, ast.ImportFrom):
                for name in node.names:
                    if (name.asname is not None and name.asname == "app") or (
                        name.asname is None and name.name == "app"
                    ):
                        return
        raise ExtensionError(
            "flask application can not be imported from app:app, "
            "no variable named app in app.py"
        )

    @override
    def check_project(self):
        """Ensure this extension can apply to the current rockcraft project."""
        if not (self.project_root / "requirements.txt").exists():
            raise ExtensionError(
                "missing requirements.txt file, "
                "flask-framework extension requires this file with flask specified as a dependency"
            )
        if not self.yaml_data.get("services", {}).get("flask", {}).get("command"):
            self._check_wsgi_path()
