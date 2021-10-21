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

from collections import OrderedDict

from twisted.internet import defer
from twisted.trial import unittest

from buildbot import config
from buildbot.process.properties import Interpolate
from buildbot.process.results import SUCCESS
from buildbot.steps.package.rpm import rpmbuild
from buildbot.test.fake.remotecommand import ExpectShell
from buildbot.test.util import steps
from buildbot.test.util.misc import TestReactorMixin


class RpmBuild(steps.BuildStepMixin, TestReactorMixin, unittest.TestCase):

    def setUp(self):
        self.setUpTestReactor()
        return self.setUpBuildStep()

    def tearDown(self):
        return self.tearDownBuildStep()

    def test_no_specfile(self):
        with self.assertRaises(config.ConfigErrors):
            rpmbuild.RpmBuild()

    def test_success(self):
        self.setupStep(rpmbuild.RpmBuild(specfile="foo.spec", dist=".el5"))
        self.expectCommands(
            ExpectShell(workdir='wkdir', command='rpmbuild --define "_topdir '
                        '`pwd`" --define "_builddir `pwd`" --define "_rpmdir '
                        '`pwd`" --define "_sourcedir `pwd`" --define "_specdir '
                        '`pwd`" --define "_srcrpmdir `pwd`" --define "dist .el5" '
                        '-ba foo.spec')
            .add(ExpectShell.log('stdio', stdout='lalala'))
            .add(0))
        self.expectOutcome(result=SUCCESS, state_string='RPMBUILD')
        return self.runStep()

    def test_autoRelease(self):
        self.setupStep(rpmbuild.RpmBuild(specfile="foo.spec", autoRelease=True))
        self.expectCommands(
            ExpectShell(workdir='wkdir', command='rpmbuild --define "_topdir '
                        '`pwd`" --define "_builddir `pwd`" --define "_rpmdir `pwd`" '
                        '--define "_sourcedir `pwd`" --define "_specdir `pwd`" '
                        '--define "_srcrpmdir `pwd`" --define "_release 0" '
                        '--define "dist .el6" -ba foo.spec')
            .add(ExpectShell.log('stdio', stdout='Your code has been rated at 10/10'))
            .add(0))
        self.expectOutcome(result=SUCCESS, state_string='RPMBUILD')
        return self.runStep()

    def test_define(self):
        defines = [("a", "1"), ("b", "2")]
        self.setupStep(rpmbuild.RpmBuild(specfile="foo.spec",
                                         define=OrderedDict(defines)))
        self.expectCommands(
            ExpectShell(workdir='wkdir', command='rpmbuild --define "_topdir '
                        '`pwd`" --define "_builddir `pwd`" --define "_rpmdir '
                        '`pwd`" --define "_sourcedir `pwd`" --define '
                        '"_specdir `pwd`" --define "_srcrpmdir `pwd`" '
                        '--define "a 1" --define "b 2" --define "dist .el6" '
                        '-ba foo.spec')
            .add(ExpectShell.log('stdio', stdout='Your code has been rated at 10/10'))
            .add(0))
        self.expectOutcome(result=SUCCESS, state_string='RPMBUILD')
        return self.runStep()

    def test_define_none(self):
        self.setupStep(rpmbuild.RpmBuild(specfile="foo.spec", define=None))
        self.expectCommands(
            ExpectShell(workdir='wkdir', command='rpmbuild --define "_topdir '
                        '`pwd`" --define "_builddir `pwd`" --define "_rpmdir '
                        '`pwd`" --define "_sourcedir `pwd`" --define '
                        '"_specdir `pwd`" --define "_srcrpmdir `pwd`" '
                        '--define "dist .el6" -ba foo.spec')
            .add(ExpectShell.log('stdio', stdout='Your code has been rated at 10/10'))
            .add(0))
        self.expectOutcome(result=SUCCESS, state_string='RPMBUILD')
        return self.runStep()

    @defer.inlineCallbacks
    def test_renderable_dist(self):
        self.setupStep(rpmbuild.RpmBuild(specfile="foo.spec",
                                         dist=Interpolate('%(prop:renderable_dist)s')))
        self.properties.setProperty('renderable_dist', '.el7', 'test')
        self.expectCommands(
            ExpectShell(workdir='wkdir', command='rpmbuild --define "_topdir '
                        '`pwd`" --define "_builddir `pwd`" --define "_rpmdir '
                        '`pwd`" --define "_sourcedir `pwd`" --define "_specdir '
                        '`pwd`" --define "_srcrpmdir `pwd`" --define "dist .el7" '
                        '-ba foo.spec')
            .add(ExpectShell.log('stdio', stdout='lalala'))
            .add(0))
        self.expectOutcome(result=SUCCESS, state_string='RPMBUILD')
        yield self.runStep()
