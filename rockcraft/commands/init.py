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
import textwrap
from pathlib import Path
from typing import TYPE_CHECKING

from craft_cli import BaseCommand, emit
from overrides import overrides

from rockcraft import errors

if TYPE_CHECKING:
    import argparse


TEMPLATES = {
    "simple": textwrap.dedent(
        """\
            name: my-rock-name # the name of your ROCK
            base: ubuntu:22.04 # the base environment for this ROCK
            version: '0.1' # just for humans. Semantic versioning is recommended
            summary: Single-line elevator pitch for your amazing ROCK # 79 char long summary
            description: |
                This is my my-rock-name's description. You have a paragraph or two to tell the
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
    "flask": textwrap.dedent(
        """\
            name: my-flask-app # the name of your Flask application
            base: ubuntu:22.04 # the base environment for this Flask application
            version: '0.1' # just for humans. Semantic versioning is recommended
            summary: A summary of your Flask application # 79 char long summary
            description: |
                This is my my-flask-app's description. You have a paragraph or two to tell the
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


class InitCommand(BaseCommand):
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
            "--profile",
            choices=list(TEMPLATES),
            default=DEFAULT_PROFILE,
            help=f"Use the specified project profile (defaults to '{DEFAULT_PROFILE}')",
        )

    @overrides
    def run(self, parsed_args: "argparse.Namespace") -> None:
        """Run the command."""
        init(TEMPLATES[parsed_args.profile])
