# This file is part of Buildbot.  Buildbot is free software: you can
# redistribute it and/or modify it under the terms of the GNU General Public
# License as published by the Free Software Foundation, version 2.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE.  See the GNU General Public License for more
# details.
#
# You should have received a copy of the GNU General Public License along with
# this program; if not, write to the Free Software Foundation, Inc., 51
# Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#
# Copyright Buildbot Team Members


from __future__ import annotations

from typing import TYPE_CHECKING
from typing import Any
from typing import Callable

from buildbot.config.checks import check_markdown_support
from buildbot.config.checks import check_param_length
from buildbot.config.checks import check_param_str_none
from buildbot.config.errors import error
from buildbot.db import model_config
from buildbot.util import bytes2unicode
from buildbot.util import config as util_config
from buildbot.util import safeTranslate

if TYPE_CHECKING:
    from buildbot.process.build import Build
    from buildbot.process.builder import CollapseRequestFn


RESERVED_UNDERSCORE_NAMES = ["__Janitor"]


class BuilderConfig(util_config.ConfiguredMixin):
    def __init__(
        self,
        name: str | bytes | None = None,
        workername: str | None = None,
        workernames: list[str] | str | None = None,
        builddir: str | None = None,
        workerbuilddir: str | None = None,
        factory: Any = None,
        tags: list[str] | None = None,
        nextWorker: Callable | None = None,
        nextBuild: Callable | None = None,
        locks: list | None = None,
        env: dict | None = None,
        properties: dict | None = None,
        collapseRequests: bool | CollapseRequestFn | None = None,
        description: str | None = None,
        description_format: str | None = None,
        canStartBuild: Callable | None = None,
        defaultProperties: dict | None = None,
        project: str | None = None,
        do_build_if: Callable[[Build], bool] | None = None,
    ) -> None:
        # name is required, and can't start with '_'
        if not name or type(name) not in (bytes, str):
            error("builder's name is required")
            name = '<unknown>'
        elif name[0] == '_' and name not in RESERVED_UNDERSCORE_NAMES:
            error(f"builder names must not start with an underscore: {name!r}")
        try:
            self.name = bytes2unicode(name, encoding="ascii")
        except UnicodeDecodeError:
            error("builder names must be unicode or ASCII")

        if not isinstance(project, (type(None), str)):
            error("builder project must be None or str")
            project = None
        self.project = project

        # factory is required
        if factory is None:
            error(f"builder {self.name!r}: has no factory")
        from buildbot.process.factory import BuildFactory

        if factory is not None and not isinstance(factory, BuildFactory):
            error(f"builder {self.name!r}: factory is not a BuildFactory instance")
        self.factory = factory

        # workernames can be a single worker name or a list, and should also
        # include workername, if given
        if isinstance(workernames, str):
            workernames = [workernames]
        if workernames:
            if not isinstance(workernames, list):
                error(f"builder {self.name!r}: workernames must be a list or a string")
        else:
            workernames = []

        if workername:
            if not isinstance(workername, str):
                error(
                    f"builder {self.name!r}: workername must be a string but it is {workername!r}"
                )
            workernames = [*workernames, workername]
        if not workernames:
            error(f"builder {self.name!r}: at least one workername is required")

        self.workernames = workernames

        # builddir defaults to name
        if builddir is None:
            builddir = safeTranslate(name)
            builddir = bytes2unicode(builddir)
        self.builddir = builddir

        # workerbuilddir defaults to builddir
        if workerbuilddir is None:
            workerbuilddir = builddir
        self.workerbuilddir = workerbuilddir

        # remainder are optional
        if tags:
            if not isinstance(tags, list):
                error(f"builder {self.name!r}: tags must be a list")
            bad_tags = any(tag for tag in tags if not isinstance(tag, str))
            if bad_tags:
                error(f"builder {self.name!r}: tags list contains something that is not a string")

            if len(tags) != len(set(tags)):
                dupes = " ".join({x for x in tags if tags.count(x) > 1})
                error(f"builder {self.name!r}: tags list contains duplicate tags: {dupes}")
        else:
            tags = []

        self.tags = tags

        self.nextWorker = nextWorker
        if nextWorker and not callable(nextWorker):
            error('nextWorker must be a callable')
        self.nextBuild = nextBuild
        if nextBuild and not callable(nextBuild):
            error('nextBuild must be a callable')
        self.canStartBuild = canStartBuild
        if canStartBuild and not callable(canStartBuild):
            error('canStartBuild must be a callable')

        self.locks = locks or []
        self.env = env or {}
        if not isinstance(self.env, dict):
            error("builder's env must be a dictionary")

        self.properties = properties or {}
        for property_name in self.properties:
            check_param_length(
                property_name, f'Builder {self.name} property', model_config.property_name_length
            )

        self.defaultProperties = defaultProperties or {}
        for property_name in self.defaultProperties:
            check_param_length(
                property_name,
                f'Builder {self.name} default property',
                model_config.property_name_length,
            )

        self.collapseRequests = collapseRequests

        self.description = check_param_str_none(description, self.__class__, "description")
        self.description_format = check_param_str_none(
            description_format, self.__class__, "description_format"
        )

        if self.description_format is None:
            pass
        elif self.description_format == "markdown":
            if not check_markdown_support(self.__class__):  # pragma: no cover
                self.description_format = None
        else:
            error("builder description format must be None or \"markdown\"")
            self.description_format = None

        if do_build_if is not None:
            self.do_build_if = do_build_if
        else:
            self.do_build_if = lambda x: True

    def getConfigDict(self) -> dict:
        # note: this method will disappear eventually - put your smarts in the
        # constructor!
        rv = {
            'name': self.name,
            'workernames': self.workernames,
            'factory': self.factory,
            'builddir': self.builddir,
            'workerbuilddir': self.workerbuilddir,
        }
        if self.project:
            rv['project'] = self.project
        if self.tags:
            rv['tags'] = self.tags
        if self.nextWorker:
            rv['nextWorker'] = self.nextWorker
        if self.nextBuild:
            rv['nextBuild'] = self.nextBuild
        if self.locks:
            rv['locks'] = self.locks
        if self.env:
            rv['env'] = self.env
        if self.properties:
            rv['properties'] = self.properties
        if self.defaultProperties:
            rv['defaultProperties'] = self.defaultProperties
        if self.collapseRequests is not None:
            rv['collapseRequests'] = self.collapseRequests
        if self.description:
            rv['description'] = self.description
            if self.description_format:
                rv['description_format'] = self.description_format
        return rv
