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
import textwrap

import pytest

from rockcraft import extensions
from rockcraft.errors import ExtensionError


@pytest.fixture
def flask_extension(mock_extensions, monkeypatch):
    monkeypatch.setenv("ROCKCRAFT_ENABLE_EXPERIMENTAL_EXTENSIONS", "1")
    extensions.register("flask-framework", extensions.flask_framework.FlaskFramework)


@pytest.fixture(name="input_yaml")
def input_yaml_fixture():
    return {"base": "ubuntu@22.04", "extensions": ["flask-framework"]}


@pytest.mark.usefixtures("flask_extension")
def test_flask_extension_default(tmp_path, input_yaml):
    (tmp_path / "requirements.txt").write_text("flask")
    (tmp_path / "app.py").write_text("app = object()")
    (tmp_path / "static").mkdir()
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "test").write_text("test")
    applied = extensions.apply_extensions(tmp_path, input_yaml)
    assert applied == {
        "base": "ubuntu@22.04",
        "parts": {
            "flask-framework/dependencies": {
                "plugin": "python",
                "python-packages": ["gunicorn"],
                "python-requirements": ["requirements.txt"],
                "source": ".",
                "stage-packages": ["python3-venv"],
            },
            "flask-framework/gunicorn-config": {
                "plugin": "nil",
                "override-build": textwrap.dedent(
                    """\
                    #!/bin/bash
                    craftctl default
                    mkdir -p $CRAFT_PART_INSTALL/flask/
                    GUNICORN_CONFIG=$CRAFT_PART_INSTALL/flask/gunicorn.conf.py
                    echo 'bind = ["0.0.0.0:8000"]' > $GUNICORN_CONFIG
                    echo 'chdir = "/flask/app"' >> $GUNICORN_CONFIG
                    """
                ),
            },
            "flask-framework/install-app": {
                "organize": {
                    "app.py": "flask/app/app.py",
                    "static": "flask/app/static",
                },
                "plugin": "dump",
                "prime": ["flask/app/app.py", "flask/app/static"],
                "source": ".",
                "stage": ["flask/app/app.py", "flask/app/static"],
            },
            "flask-framework/misc": {
                "plugin": "nil",
                "source": ".",
                "stage-packages": ["ca-certificates_data"],
            },
        },
        "platforms": {"amd64": {}},
        "run_user": "_daemon_",
        "services": {
            "flask": {
                "command": "/bin/python3 -m gunicorn -c /flask/gunicorn.conf.py app:app",
                "override": "replace",
                "startup": "enabled",
                "user": "_daemon_",
            }
        },
    }


@pytest.mark.usefixtures("flask_extension")
def test_flask_extension_prime_override(tmp_path, input_yaml):
    (tmp_path / "requirements.txt").write_text("flask")
    (tmp_path / "app.py").write_text("app = object()")
    (tmp_path / "static").mkdir()
    (tmp_path / "node_modules").mkdir()

    input_yaml["parts"] = {
        "flask-framework/install-app": {
            "prime": [
                "flask/app/app.py",
                "flask/app/requirements.txt",
                "flask/app/static",
            ]
        }
    }
    applied = extensions.apply_extensions(tmp_path, input_yaml)
    install_app_part = applied["parts"]["flask-framework/install-app"]
    assert install_app_part["prime"] == [
        "flask/app/app.py",
        "flask/app/requirements.txt",
        "flask/app/static",
    ]
    assert install_app_part["organize"] == {
        "app.py": "flask/app/app.py",
        "requirements.txt": "flask/app/requirements.txt",
        "static": "flask/app/static",
    }
    assert install_app_part["stage"] == [
        "flask/app/app.py",
        "flask/app/requirements.txt",
        "flask/app/static",
    ]


@pytest.mark.usefixtures("flask_extension")
def test_flask_framework_exclude_prime(tmp_path, input_yaml):
    (tmp_path / "requirements.txt").write_text("flask")
    (tmp_path / "app.py").write_text("app = object()")
    (tmp_path / "static").mkdir()
    (tmp_path / "webapp").mkdir()
    (tmp_path / "test").mkdir()
    (tmp_path / "node_modules").mkdir()
    input_yaml["parts"] = {
        "flask-framework/install-app": {
            "prime": [
                "- flask/app/test",
            ]
        }
    }
    applied = extensions.apply_extensions(tmp_path, input_yaml)
    install_app_part = applied["parts"]["flask-framework/install-app"]
    assert install_app_part["prime"] == ["- flask/app/test"]
    assert install_app_part["organize"] == {
        "app.py": "flask/app/app.py",
        "requirements.txt": "flask/app/requirements.txt",
        "static": "flask/app/static",
        "test": "flask/app/test",
        "webapp": "flask/app/webapp",
    }
    assert install_app_part["stage"] == [
        "flask/app/app.py",
        "flask/app/requirements.txt",
        "flask/app/static",
        "flask/app/test",
        "flask/app/webapp",
    ]


@pytest.mark.usefixtures("flask_extension")
def test_flask_framework_service_override(tmp_path, input_yaml):
    (tmp_path / "requirements.txt").write_text("flask")
    (tmp_path / "app.py").write_text("app = object()")
    input_yaml["services"] = {
        "flask": {
            "command": "/bin/python3 -m gunicorn -c /flask/gunicorn.conf.py webapp:app"
        }
    }

    applied = extensions.apply_extensions(tmp_path, input_yaml)
    assert applied["services"]["flask"] == {
        "command": "/bin/python3 -m gunicorn -c /flask/gunicorn.conf.py webapp:app",
        "override": "replace",
        "startup": "enabled",
        "user": "_daemon_",
    }


@pytest.mark.usefixtures("flask_extension")
def test_flask_framework_add_service(tmp_path, input_yaml):
    (tmp_path / "requirements.txt").write_text("flask")
    (tmp_path / "app.py").write_text("app = object()")
    input_yaml["services"] = {
        "foobar": {
            "command": "/bin/foobar",
            "override": "replace",
        },
    }

    applied = extensions.apply_extensions(tmp_path, input_yaml)
    assert applied["services"] == {
        "flask": {
            "command": "/bin/python3 -m gunicorn -c /flask/gunicorn.conf.py app:app",
            "override": "replace",
            "startup": "enabled",
            "user": "_daemon_",
        },
        "foobar": {
            "command": "/bin/foobar",
            "override": "replace",
        },
    }


@pytest.mark.usefixtures("flask_extension")
def test_flask_extension_override_parts(tmp_path, input_yaml):
    (tmp_path / "requirements.txt").write_text("flask")
    (tmp_path / "foobar").touch()
    (tmp_path / "app.py").write_text("app = object()")
    (tmp_path / "static").mkdir()
    (tmp_path / "node_modules").mkdir()

    input_yaml["parts"] = {
        "flask-framework/install-app": {"prime": ["-flask/app/foobar"]},
        "flask-framework/dependencies": {
            "python-requirements": ["requirements-jammy.txt"]
        },
    }
    applied = extensions.apply_extensions(tmp_path, input_yaml)

    assert applied["parts"]["flask-framework/install-app"]["prime"] == [
        "-flask/app/foobar"
    ]

    assert applied["parts"]["flask-framework/dependencies"] == {
        "plugin": "python",
        "python-packages": ["gunicorn"],
        "python-requirements": ["requirements.txt", "requirements-jammy.txt"],
        "source": ".",
        "stage-packages": ["python3-venv"],
    }


@pytest.mark.usefixtures("flask_extension")
def test_flask_extension_bare(tmp_path):
    (tmp_path / "requirements.txt").write_text("flask")
    (tmp_path / "app.py").write_text("app = object()")
    input_yaml = {
        "extensions": ["flask-framework"],
        "base": "bare",
        "parts": {"flask/install-app": {"prime": ["-flask/app/.git"]}},
    }
    applied = extensions.apply_extensions(tmp_path, input_yaml)
    assert applied["parts"]["flask-framework/misc"] == {
        "plugin": "nil",
        "source": ".",
        "override-build": "mkdir -m 777 ${CRAFT_PART_INSTALL}/tmp",
        "stage-packages": ["bash_bins", "coreutils_bins", "ca-certificates_data"],
    }
    assert applied["build-base"] == "ubuntu@22.04"


@pytest.mark.usefixtures("flask_extension")
def test_flask_extension_no_requirements_txt_error(tmp_path):
    (tmp_path / "app.py").write_text("app = object()")
    input_yaml = {"extensions": ["flask-framework"], "base": "bare"}
    with pytest.raises(ExtensionError) as exc:
        extensions.apply_extensions(tmp_path, input_yaml)
    assert "requirements.txt" in str(exc)


@pytest.mark.usefixtures("flask_extension")
def test_flask_extension_incorrect_prime_prefix_error(tmp_path):
    (tmp_path / "requirements.txt").write_text("flask")
    (tmp_path / "app.py").write_text("app = object()")
    input_yaml = {
        "extensions": ["flask-framework"],
        "base": "bare",
        "parts": {"flask-framework/install-app": {"prime": ["app.py"]}},
    }
    (tmp_path / "requirements.txt").write_text("flask")

    with pytest.raises(ExtensionError) as exc:
        extensions.apply_extensions(tmp_path, input_yaml)
    assert "flask/app" in str(exc)


@pytest.mark.usefixtures("flask_extension")
def test_flask_extension_incorrect_wsgi_path_error(tmp_path):
    input_yaml = {
        "extensions": ["flask-framework"],
        "base": "bare",
        "parts": {"flask/install-app": {"prime": ["flask/app/requirement.txt"]}},
    }
    (tmp_path / "requirements.txt").write_text("flask")

    with pytest.raises(ExtensionError) as exc:
        extensions.apply_extensions(tmp_path, input_yaml)
    assert "app:app" in str(exc)

    (tmp_path / "app.py").write_text("flask")

    with pytest.raises(ExtensionError) as exc:
        extensions.apply_extensions(tmp_path, input_yaml)
    assert "app:app" in str(exc)


@pytest.mark.usefixtures("flask_extension")
def test_flask_extension_flask_service_override_disable_wsgi_path_check(tmp_path):
    (tmp_path / "requirements.txt").write_text("flask")

    input_yaml = {
        "extensions": ["flask-framework"],
        "base": "bare",
        "services": {
            "flask": {
                "command": "/bin/python3 -m gunicorn -c /flask/gunicorn.conf.py webapp:app"
            }
        },
    }

    extensions.apply_extensions(tmp_path, input_yaml)
