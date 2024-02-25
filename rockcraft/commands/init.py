# -*- Mode:Python; indent-tabs-mode:nil; tab-width:4 -*-
#
# Copyright 2022 Canonical Ltd.
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

"""Creation of minimalist rockcraft projects."""
import pathlib
import re
import textwrap
from pathlib import Path
from typing import TYPE_CHECKING

from craft_application.commands import AppCommand
from craft_cli import emit
from overrides import overrides  # type: ignore[reportUnknownVariableType]

from rockcraft import errors
from rockcraft.models.project import INVALID_NAME_MESSAGE, NAME_REGEX

if TYPE_CHECKING:
    import argparse

TEMPLATES = {
    "simple": textwrap.dedent(
        """\
            name: {name}
            base: ubuntu@22.04 # the base environment for this ROCK
            version: '0.1' # just for humans. Semantic versioning is recommended
            summary: Single-line elevator pitch for your amazing ROCK # 79 char long summary
            description: |
                This is {name}'s description. You have a paragraph or two to tell the
                most important story about it. Keep it under 100 words though,
                we live in tweetspace and your description wants to look good in the
                container registries out there.
            license: GPL-3.0 # your application's SPDX license
            platforms: # The platforms this ROCK should be built on and run on
                amd64:

            parts:
                my-part:
                    plugin: nil
            """
    ),
    "flask-framework": textwrap.dedent(
        """\
            name: {name}
            base: ubuntu@22.04 # the base environment for this Flask application
            version: '0.1' # just for humans. Semantic versioning is recommended
            summary: A summary of your Flask application # 79 char long summary
            description: |
                This is {name}'s description. You have a paragraph or two to tell the
                most important story about it. Keep it under 100 words though,
                we live in tweetspace and your description wants to look good in the
                container registries out there.
            license: GPL-3.0 # your application's SPDX license
            platforms: # The platforms this ROCK should be built on and run on
                amd64:

            # To ensure the flask-framework extension works properly, your Flask application
            # should have an `app.py` file with an `app` object as the WSGI entrypoint.
            extensions:
                - flask-framework


            # Uncomment the sections you need and adjust according to your requirements.
            # parts:
            #   flask-framework/dependencies:
            #     stage-packages:
            #       # list required packages or slices for your flask application below.
            #       - libpq-dev
            #
            #   flask-framework/install-app:
            #     prime:
            #       # By default, only the files in app/, templates/, static/, and app.py
            #       # are copied into the image. You can modify the list below to override
            #       # the default list and include or exclude specific files/directories
            #       # in your project.
            #       # Note: Prefix each entry with "flask/app/" followed by the local path.
            #       - flask/app/.env
            #       - flask/app/app.py
            #       - flask/app/webapp
            #       - flask/app/templates
            #       - flask/app/static
            """
    ),
    "django-framework": textwrap.dedent(
        """\
            name: {name}
            base: ubuntu@22.04 # the base environment for this Django application
            version: '0.1' # just for humans. Semantic versioning is recommended
            summary: A summary of your Flask application # 79 char long summary
            description: |
                This is {name}'s description. You have a paragraph or two to tell the
                most important story about it. Keep it under 100 words though,
                we live in tweetspace and your description wants to look good in the
                container registries out there.
            license: GPL-3.0 # your application's SPDX license
            platforms: # The platforms this ROCK should be built on and run on
                amd64:
    
            # To ensure the django-framework extension works properly, your Django project should
            # locate in ./{snake_name}, and have an ./{snake_name}/{snake_name}/wsgi.py file 
            # with an `application` object as the WSGI entrypoint
            extensions:
                - django-framework

            # Uncomment the sections you need and adjust according to your requirements.
            # parts:
            #   django-framework/dependencies:
            #     stage-packages:
            #       # list required packages or slices for your flask application below.
            #       - libpq-dev
            """
    ),
}

DEFAULT_PROFILE = "simple"


def init(rockcraft_yaml_content: str) -> None:
    """Initialize a rockcraft project.

    :param rockcraft_yaml_content: Content of the rockcraft.yaml file
    :raises RockcraftInitError: raises initialization error in case of conflicts
    with existing rockcraft.yaml files
    """
    rockcraft_yaml_path = Path("rockcraft.yaml")

    if rockcraft_yaml_path.is_file():
        raise errors.RockcraftInitError(f"{rockcraft_yaml_path} already exists!")

    if Path(f".{rockcraft_yaml_path.name}").is_file():
        raise errors.RockcraftInitError(f".{rockcraft_yaml_path} already exists!")

    rockcraft_yaml_path.write_text(rockcraft_yaml_content)

    emit.progress(f"Created {rockcraft_yaml_path}.")


class InitCommand(AppCommand):
    """Initialize a rockcraft project."""

    name = "init"
    help_msg = "Initialize a rockcraft project"
    overview = textwrap.dedent(
        """
        Initialize a rockcraft project by creating a minimalist,
        yet functional, rockcraft.yaml file in the current directory.
        """
    )

    def fill_parser(self, parser):
        """Specify command's specific parameters."""
        parser.add_argument(
            "--name", help="The name of the ROCK; defaults to the directory name"
        )
        parser.add_argument(
            "--profile",
            choices=list(TEMPLATES),
            default=DEFAULT_PROFILE,
            help=f"Use the specified project profile (defaults to '{DEFAULT_PROFILE}')",
        )

    @overrides
    def run(self, parsed_args: "argparse.Namespace") -> None:
        """Run the command."""
        name = parsed_args.name
        if name and not re.match(NAME_REGEX, name):
            raise errors.RockcraftInitError(
                f"'{name}' is not a valid rock name. " + INVALID_NAME_MESSAGE
            )

        if not name:
            name = pathlib.Path.cwd().name
            if not re.match(NAME_REGEX, name):
                name = "my-rock-name"
            emit.debug(f"Set project name to '{name}'")

        context = {"name": name, "snake_name": name.replace("-", "_").lower()}

        init(TEMPLATES[parsed_args.profile].format(**context))
