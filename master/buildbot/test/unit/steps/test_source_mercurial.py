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

from twisted.internet import error
from twisted.python.reflect import namedModule
from twisted.trial import unittest

from buildbot import config
from buildbot.process import remotetransfer
from buildbot.process.results import FAILURE
from buildbot.process.results import RETRY
from buildbot.process.results import SUCCESS
from buildbot.steps.source import mercurial
from buildbot.test.fake.remotecommand import Expect
from buildbot.test.fake.remotecommand import ExpectRemoteRef
from buildbot.test.fake.remotecommand import ExpectShell
from buildbot.test.util import sourcesteps
from buildbot.test.util.misc import TestReactorMixin


class TestMercurial(sourcesteps.SourceStepMixin, TestReactorMixin,
                    unittest.TestCase):

    def setUp(self):
        self.setUpTestReactor()
        return self.setUpSourceStep()

    def tearDown(self):
        return self.tearDownSourceStep()

    def patch_workerVersionIsOlderThan(self, result):
        self.patch(
            mercurial.Mercurial, 'workerVersionIsOlderThan', lambda x, y, z: result)

    def test_no_repourl(self):
        with self.assertRaises(config.ConfigErrors):
            mercurial.Mercurial(mode="full")

    def test_incorrect_mode(self):
        with self.assertRaises(config.ConfigErrors):
            mercurial.Mercurial(repourl='http://hg.mozilla.org', mode='invalid')

    def test_incorrect_method(self):
        with self.assertRaises(config.ConfigErrors):
            mercurial.Mercurial(repourl='http://hg.mozilla.org',
                                method='invalid')

    def test_incorrect_branchType(self):
        with self.assertRaises(config.ConfigErrors):
            mercurial.Mercurial(repourl='http://hg.mozilla.org',
                                branchType='invalid')

    def test_mode_full_clean(self):
        self.setupStep(
            mercurial.Mercurial(repourl='http://hg.mozilla.org',
                                mode='full', method='clean', branchType='inrepo'))
        self.expectCommands(
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', '--version'])
            .add(0),
            Expect('stat', dict(file='wkdir/.buildbot-patched',
                                logEnviron=True))
            .add(1),
            Expect('stat', dict(file='wkdir/.hg',
                                logEnviron=True))
            .add(0),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', '--config',
                                 'extensions.purge=', 'purge'])
            .add(0),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'pull',
                                 'http://hg.mozilla.org', '--rev', 'default'])
            .add(0),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'identify', '--branch'])
            .add(ExpectShell.log('stdio', stdout='default'))
            .add(0),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'locate', 'set:added()'])
            .add(1),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'update',
                                 '--clean', '--rev', 'default'])
            .add(0),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'parents',
                                 '--template', '{node}\\n'])
            .add(ExpectShell.log('stdio', stdout='\n'))
            .add(ExpectShell.log('stdio', stdout='f6ad368298bd941e934a41f3babc827b2aa95a1d'))
            .add(0)
        )
        self.expectOutcome(result=SUCCESS)
        return self.runStep()

    def test_mode_full_clean_win32path(self):
        self.setupStep(
            mercurial.Mercurial(repourl='http://hg.mozilla.org',
                                mode='full', method='clean', branchType='inrepo'))
        self.build.path_module = namedModule('ntpath')
        self.expectCommands(
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', '--version'])
            .add(0),
            Expect('stat', dict(file=r'wkdir\.buildbot-patched',
                                logEnviron=True))
            .add(1),
            Expect('stat', dict(file=r'wkdir\.hg',
                                logEnviron=True))
            .add(0),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', '--config',
                                 'extensions.purge=', 'purge'])
            .add(0),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'pull',
                                 'http://hg.mozilla.org', '--rev', 'default'])
            .add(0),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'identify', '--branch'])
            .add(ExpectShell.log('stdio', stdout='default'))
            .add(0),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'locate', 'set:added()'])
            .add(1),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'update',
                                 '--clean', '--rev', 'default'])
            .add(0),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'parents',
                                 '--template', '{node}\\n'])
            .add(ExpectShell.log('stdio', stdout='\n'))
            .add(ExpectShell.log('stdio', stdout='f6ad368298bd941e934a41f3babc827b2aa95a1d'))
            .add(0)
        )
        self.expectOutcome(result=SUCCESS)
        return self.runStep()

    def test_mode_full_clean_timeout(self):
        self.setupStep(
            mercurial.Mercurial(repourl='http://hg.mozilla.org',
                                timeout=1,
                                mode='full', method='clean', branchType='inrepo'))
        self.expectCommands(
            ExpectShell(workdir='wkdir',
                        timeout=1,
                        command=['hg', '--verbose', '--version'])
            .add(0),
            Expect('stat', dict(file='wkdir/.buildbot-patched',
                                logEnviron=True))
            .add(1),
            Expect('stat', dict(file='wkdir/.hg',
                                logEnviron=True))
            .add(0),
            ExpectShell(workdir='wkdir',
                        timeout=1,
                        command=['hg', '--verbose', '--config',
                                 'extensions.purge=', 'purge'])
            .add(0),
            ExpectShell(workdir='wkdir',
                        timeout=1,
                        command=['hg', '--verbose', 'pull',
                                 'http://hg.mozilla.org', '--rev', 'default'])
            .add(0),
            ExpectShell(workdir='wkdir',
                        timeout=1,
                        command=['hg', '--verbose', 'identify', '--branch'])
            .add(ExpectShell.log('stdio', stdout='default'))
            .add(0),
            ExpectShell(workdir='wkdir',
                        timeout=1,
                        command=['hg', '--verbose', 'locate', 'set:added()'])
            .add(1),
            ExpectShell(workdir='wkdir',
                        timeout=1,
                        command=['hg', '--verbose', 'update',
                                 '--clean', '--rev', 'default'])
            .add(0),
            ExpectShell(workdir='wkdir',
                        timeout=1,
                        command=['hg', '--verbose', 'parents',
                                 '--template', '{node}\\n'])
            .add(ExpectShell.log('stdio', stdout='\n'))
            .add(ExpectShell.log('stdio', stdout='f6ad368298bd941e934a41f3babc827b2aa95a1d'))
            .add(0)
        )
        self.expectOutcome(result=SUCCESS)
        return self.runStep()

    def test_mode_full_clean_patch(self):
        self.setupStep(
            mercurial.Mercurial(repourl='http://hg.mozilla.org',
                                mode='full', method='clean', branchType='inrepo'),
            patch=(1, 'patch'))
        self.expectCommands(
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', '--version'])
            .add(0),
            Expect('stat', dict(file='wkdir/.buildbot-patched',
                                logEnviron=True))
            .add(0),
            Expect('stat', dict(file='wkdir/.hg',
                                logEnviron=True))
            .add(0),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', '--config',
                                 'extensions.purge=', 'purge'])
            .add(0),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'pull',
                                 'http://hg.mozilla.org', '--rev', 'default'])
            .add(0),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'identify', '--branch'])
            .add(ExpectShell.log('stdio', stdout='default'))
            .add(0),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'locate', 'set:added()'])
            .add(1),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'update',
                                 '--clean', '--rev', 'default'])
            .add(0),
            Expect('downloadFile', dict(blocksize=32768, maxsize=None,
                                        reader=ExpectRemoteRef(
                                            remotetransfer.StringFileReader),
                                        workerdest='.buildbot-diff', workdir='wkdir',
                                        mode=None))
            .add(0),
            Expect('downloadFile', dict(blocksize=32768, maxsize=None,
                                        reader=ExpectRemoteRef(
                                            remotetransfer.StringFileReader),
                                        workerdest='.buildbot-patched', workdir='wkdir',
                                        mode=None))
            .add(0),
            ExpectShell(workdir='wkdir',
                        command=[
                            'hg', '--verbose', 'import', '--no-commit', '-p', '1', '-'],
                        initialStdin='patch')
            .add(0),
            Expect('rmdir', dict(dir='wkdir/.buildbot-diff',
                                 logEnviron=True))
            .add(0),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'parents',
                                 '--template', '{node}\\n'])
            .add(ExpectShell.log('stdio', stdout='\n'))
            .add(ExpectShell.log('stdio', stdout='f6ad368298bd941e934a41f3babc827b2aa95a1d'))
            .add(0)
        )
        self.expectOutcome(result=SUCCESS)
        return self.runStep()

    def test_mode_full_clean_patch_worker_2_16(self):
        self.setupStep(
            mercurial.Mercurial(repourl='http://hg.mozilla.org',
                                mode='full', method='clean', branchType='inrepo'),
            patch=(1, 'patch'),
            worker_version={'*': '2.16'})
        self.expectCommands(
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', '--version'])
            .add(0),
            Expect('stat', dict(file='wkdir/.buildbot-patched',
                                logEnviron=True))
            .add(0),
            Expect('stat', dict(file='wkdir/.hg',
                                logEnviron=True))
            .add(0),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', '--config',
                                 'extensions.purge=', 'purge'])
            .add(0),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'pull',
                                 'http://hg.mozilla.org', '--rev', 'default'])
            .add(0),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'identify', '--branch'])
            .add(ExpectShell.log('stdio', stdout='default'))
            .add(0),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'locate', 'set:added()'])
            .add(1),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'update',
                                 '--clean', '--rev', 'default'])
            .add(0),
            Expect('downloadFile', dict(blocksize=32768, maxsize=None,
                                        reader=ExpectRemoteRef(
                                            remotetransfer.StringFileReader),
                                        slavedest='.buildbot-diff', workdir='wkdir',
                                        mode=None))
            .add(0),
            Expect('downloadFile', dict(blocksize=32768, maxsize=None,
                                        reader=ExpectRemoteRef(
                                            remotetransfer.StringFileReader),
                                        slavedest='.buildbot-patched', workdir='wkdir',
                                        mode=None))
            .add(0),
            ExpectShell(workdir='wkdir',
                        command=[
                            'hg', '--verbose', 'import', '--no-commit', '-p', '1', '-'],
                        initialStdin='patch')
            .add(0),
            Expect('rmdir', dict(dir='wkdir/.buildbot-diff',
                                 logEnviron=True))
            .add(0),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'parents',
                                 '--template', '{node}\\n'])
            .add(ExpectShell.log('stdio', stdout='\n'))
            .add(ExpectShell.log('stdio', stdout='f6ad368298bd941e934a41f3babc827b2aa95a1d'))
            .add(0)
        )
        self.expectOutcome(result=SUCCESS)
        return self.runStep()

    def test_mode_full_clean_patch_fail(self):
        self.setupStep(
            mercurial.Mercurial(repourl='http://hg.mozilla.org',
                                mode='full', method='clean', branchType='inrepo'),
            patch=(1, 'patch'))
        self.expectCommands(
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', '--version'])
            .add(0),
            Expect('stat', dict(file='wkdir/.buildbot-patched',
                                logEnviron=True))
            .add(0),
            Expect('stat', dict(file='wkdir/.hg',
                                logEnviron=True))
            .add(0),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', '--config',
                                 'extensions.purge=', 'purge'])
            .add(0),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'pull',
                                 'http://hg.mozilla.org', '--rev', 'default'])
            .add(0),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'identify', '--branch'])
            .add(ExpectShell.log('stdio', stdout='default'))
            .add(0),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'locate', 'set:added()'])
            .add(1),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'update',
                                 '--clean', '--rev', 'default'])
            .add(0),
            Expect('downloadFile', dict(blocksize=32768, maxsize=None,
                                        reader=ExpectRemoteRef(
                                            remotetransfer.StringFileReader),
                                        workerdest='.buildbot-diff', workdir='wkdir',
                                        mode=None))
            .add(0),
            Expect('downloadFile', dict(blocksize=32768, maxsize=None,
                                        reader=ExpectRemoteRef(
                                            remotetransfer.StringFileReader),
                                        workerdest='.buildbot-patched', workdir='wkdir',
                                        mode=None))
            .add(0),
            ExpectShell(workdir='wkdir',
                        command=[
                            'hg', '--verbose', 'import', '--no-commit', '-p', '1', '-'],
                        initialStdin='patch')
            .add(1)
        )
        self.expectOutcome(result=FAILURE, state_string="update (failure)")
        return self.runStep()

    def test_mode_full_clean_no_existing_repo(self):
        self.setupStep(
            mercurial.Mercurial(repourl='http://hg.mozilla.org',
                                mode='full', method='clean', branchType='inrepo'))
        self.expectCommands(
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', '--version'])
            .add(0),
            Expect('stat', dict(file='wkdir/.buildbot-patched',
                                logEnviron=True))
            .add(1),
            Expect('stat', dict(file='wkdir/.hg',
                                logEnviron=True))
            .add(1),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'clone', '--noupdate',
                                 'http://hg.mozilla.org', '.'])
            .add(0),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'update',
                                 '--clean', '--rev', 'default'],
                        logEnviron=True)
            .add(0),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'parents',
                                 '--template', '{node}\\n'])
            .add(ExpectShell.log('stdio', stdout='\n'))
            .add(ExpectShell.log('stdio', stdout='f6ad368298bd941e934a41f3babc827b2aa95a1d'))
            .add(0)
        )
        self.expectOutcome(result=SUCCESS)
        return self.runStep()

    def test_mode_full_clobber(self):
        self.setupStep(
            mercurial.Mercurial(repourl='http://hg.mozilla.org',
                                mode='full', method='clobber', branchType='inrepo'))
        self.expectCommands(
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', '--version'])
            .add(0),
            Expect('stat', dict(file='wkdir/.buildbot-patched',
                                logEnviron=True))
            .add(1),
            Expect('rmdir', dict(dir='wkdir',
                                 logEnviron=True))
            .add(0),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'clone', '--noupdate',
                                 'http://hg.mozilla.org', '.'])
            .add(0),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'update',
                                 '--clean', '--rev', 'default'])
            .add(0),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'parents',
                                 '--template', '{node}\\n'])
            .add(ExpectShell.log('stdio', stdout='f6ad368298bd941e934a41f3babc827b2aa95a1d'))
            .add(0)
        )
        self.expectOutcome(result=SUCCESS)
        return self.runStep()

    def test_mode_full_fresh(self):
        self.setupStep(
            mercurial.Mercurial(repourl='http://hg.mozilla.org',
                                mode='full', method='fresh', branchType='inrepo'))
        self.expectCommands(
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', '--version'])
            .add(0),
            Expect('stat', dict(file='wkdir/.buildbot-patched',
                                logEnviron=True))
            .add(1),
            Expect('stat', dict(file='wkdir/.hg',
                                logEnviron=True))
            .add(0),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', '--config',
                                 'extensions.purge=', 'purge', '--all'])
            .add(0),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'pull',
                                 'http://hg.mozilla.org', '--rev', 'default'])
            .add(0),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'identify', '--branch'])
            .add(ExpectShell.log('stdio', stdout='default'))
            .add(0),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'locate', 'set:added()'])
            .add(1),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'update',
                                 '--clean', '--rev', 'default'])
            .add(0),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'parents',
                                 '--template', '{node}\\n'])
            .add(ExpectShell.log('stdio', stdout='\n'))
            .add(ExpectShell.log('stdio', stdout='f6ad368298bd941e934a41f3babc827b2aa95a1d'))
            .add(0)
        )
        self.expectOutcome(result=SUCCESS)
        return self.runStep()

    def test_mode_full_fresh_no_existing_repo(self):
        self.setupStep(
            mercurial.Mercurial(repourl='http://hg.mozilla.org',
                                mode='full', method='fresh', branchType='inrepo'))
        self.expectCommands(
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', '--version'])
            .add(0),
            Expect('stat', dict(file='wkdir/.buildbot-patched',
                                logEnviron=True))
            .add(1),
            Expect('stat', dict(file='wkdir/.hg',
                                logEnviron=True))
            .add(1),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'clone', '--noupdate',
                                 'http://hg.mozilla.org', '.'])
            .add(0),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'update',
                                 '--clean', '--rev', 'default'],
                        logEnviron=True)
            .add(0),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'parents',
                                 '--template', '{node}\\n'])
            .add(ExpectShell.log('stdio', stdout='\n'))
            .add(ExpectShell.log('stdio', stdout='f6ad368298bd941e934a41f3babc827b2aa95a1d'))
            .add(0)
        )
        self.expectOutcome(result=SUCCESS)
        return self.runStep()

    def test_mode_full_fresh_retry(self):
        self.setupStep(
            mercurial.Mercurial(repourl='http://hg.mozilla.org',
                                mode='full', method='fresh', branchType='inrepo',
                                retry=(0, 2)))
        self.expectCommands(
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', '--version'])
            .add(0),
            Expect('stat', dict(file='wkdir/.buildbot-patched',
                                logEnviron=True))
            .add(1),
            Expect('stat', dict(file='wkdir/.hg',
                                logEnviron=True))
            .add(1),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'clone', '--noupdate',
                                 'http://hg.mozilla.org', '.'])
            .add(1),
            Expect('rmdir', dict(dir='wkdir',
                                 logEnviron=True))
            .add(0),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'clone', '--noupdate',
                                 'http://hg.mozilla.org', '.'])
            .add(1),
            Expect('rmdir', dict(dir='wkdir',
                                 logEnviron=True))
            .add(0),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'clone', '--noupdate',
                                 'http://hg.mozilla.org', '.'])
            .add(0),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'update',
                                 '--clean', '--rev', 'default'],
                        logEnviron=True)
            .add(0),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'parents',
                                 '--template', '{node}\\n'])
            .add(ExpectShell.log('stdio', stdout='\n'))
            .add(ExpectShell.log('stdio', stdout='f6ad368298bd941e934a41f3babc827b2aa95a1d'))
            .add(0)
        )
        self.expectOutcome(result=SUCCESS)
        return self.runStep()

    def test_mode_incremental_no_existing_repo_dirname(self):
        self.setupStep(
            mercurial.Mercurial(repourl='http://hg.mozilla.org',
                                mode='incremental', branchType='dirname'),
        )
        self.expectCommands(
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', '--version'])
            .add(0),
            Expect('stat', dict(file='wkdir/.buildbot-patched',
                                logEnviron=True))
            .add(1),
            Expect('stat', dict(file='wkdir/.hg',
                                logEnviron=True))
            .add(1),  # does not exist
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'clone', '--noupdate',
                                 'http://hg.mozilla.org', '.'])
            .add(0),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'locate', 'set:added()'])
            .add(1),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'update', '--clean'])
            .add(0),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'parents',
                                 '--template', '{node}\\n'])
            .add(ExpectShell.log('stdio', stdout='\n'))
            .add(ExpectShell.log('stdio', stdout='f6ad368298bd941e934a41f3babc827b2aa95a1d'))
            .add(0)
        )
        self.expectOutcome(result=SUCCESS)
        return self.runStep()

    def test_mode_incremental_retry(self):
        self.setupStep(
            mercurial.Mercurial(repourl='http://hg.mozilla.org',
                                mode='incremental', branchType='dirname', retry=(0, 1)),
        )
        self.expectCommands(
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', '--version'])
            .add(0),
            Expect('stat', dict(file='wkdir/.buildbot-patched',
                                logEnviron=True))
            .add(1),
            Expect('stat', dict(file='wkdir/.hg',
                                logEnviron=True))
            .add(1),  # does not exist
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'clone', '--noupdate',
                                 'http://hg.mozilla.org', '.'])
            .add(1),
            Expect('rmdir', dict(dir='wkdir',
                                 logEnviron=True))
            .add(0),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'clone', '--noupdate',
                                 'http://hg.mozilla.org', '.'])
            .add(0),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'locate', 'set:added()'])
            .add(1),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'update', '--clean'])
            .add(0),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'parents',
                                 '--template', '{node}\\n'])
            .add(ExpectShell.log('stdio', stdout='\n'))
            .add(ExpectShell.log('stdio', stdout='f6ad368298bd941e934a41f3babc827b2aa95a1d'))
            .add(0)
        )
        self.expectOutcome(result=SUCCESS)
        return self.runStep()

    def test_mode_incremental_branch_change_dirname(self):
        self.setupStep(
            mercurial.Mercurial(repourl='http://hg.mozilla.org/',
                                mode='incremental', branchType='dirname', defaultBranch='devel'),
            dict(branch='stable')
        )
        self.expectCommands(
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', '--version'])
            .add(0),
            Expect('stat', dict(file='wkdir/.buildbot-patched',
                                logEnviron=True))
            .add(1),
            Expect('stat', dict(file='wkdir/.hg',
                                logEnviron=True))
            .add(0),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'pull',
                                 'http://hg.mozilla.org/stable'])
            .add(0),
            Expect('rmdir', dict(dir='wkdir',
                                 logEnviron=True))
            .add(0),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'clone', '--noupdate',
                                 'http://hg.mozilla.org/stable', '.'])
            .add(0),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'update',
                                 '--clean'])
            .add(0),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'parents',
                                 '--template', '{node}\\n'])
            .add(ExpectShell.log('stdio', stdout='\n'))
            .add(ExpectShell.log('stdio', stdout='f6ad368298bd941e934a41f3babc827b2aa95a1d'))
            .add(0)
        )
        self.expectOutcome(result=SUCCESS)
        return self.runStep()

    def test_mode_incremental_no_existing_repo_inrepo(self):
        self.setupStep(
            mercurial.Mercurial(repourl='http://hg.mozilla.org',
                                mode='incremental', branchType='inrepo'))
        self.expectCommands(
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', '--version'])
            .add(0),
            Expect('stat', dict(file='wkdir/.buildbot-patched',
                                logEnviron=True))
            .add(1),
            Expect('stat', dict(file='wkdir/.hg',
                                logEnviron=True))
            .add(1),  # does not exist
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'clone', '--noupdate',
                                 'http://hg.mozilla.org', '.'])
            .add(0),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'identify', '--branch'])
            .add(ExpectShell.log('stdio', stdout='default'))
            .add(0),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'locate', 'set:added()'])
            .add(1),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'update', '--clean',
                                 '--rev', 'default'])
            .add(0),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'parents',
                                 '--template', '{node}\\n'])
            .add(ExpectShell.log('stdio', stdout='\n'))
            .add(ExpectShell.log('stdio', stdout='f6ad368298bd941e934a41f3babc827b2aa95a1d'))
            .add(0)
        )
        self.expectOutcome(result=SUCCESS)
        return self.runStep()

    def test_mode_incremental_existing_repo(self):
        self.setupStep(
            mercurial.Mercurial(repourl='http://hg.mozilla.org',
                                mode='incremental', branchType='inrepo'))
        self.expectCommands(
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', '--version'])
            .add(0),
            Expect('stat', dict(file='wkdir/.buildbot-patched',
                                logEnviron=True))
            .add(1),
            Expect('stat', dict(file='wkdir/.hg',
                                logEnviron=True))
            .add(0),  # directory exists
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'pull',
                                 'http://hg.mozilla.org', '--rev', 'default'])
            .add(0),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'identify', '--branch'])
            .add(ExpectShell.log('stdio', stdout='default'))
            .add(0),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'locate', 'set:added()'])
            .add(1),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'update', '--clean',
                                 '--rev', 'default'])
            .add(0),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'parents',
                                 '--template', '{node}\\n'])
            .add(ExpectShell.log('stdio', stdout='\n'))
            .add(ExpectShell.log('stdio', stdout='f6ad368298bd941e934a41f3babc827b2aa95a1d'))
            .add(0)
        )
        self.expectOutcome(result=SUCCESS)
        return self.runStep()

    def test_mode_incremental_existing_repo_added_files(self):
        self.setupStep(
            mercurial.Mercurial(repourl='http://hg.mozilla.org',
                                mode='incremental', branchType='inrepo'))
        self.expectCommands(
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', '--version'])
            .add(0),
            Expect('stat', dict(file='wkdir/.buildbot-patched',
                                logEnviron=True))
            .add(1),
            Expect('stat', dict(file='wkdir/.hg',
                                logEnviron=True))
            .add(0),  # directory exists
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'pull',
                                 'http://hg.mozilla.org', '--rev', 'default'])
            .add(0),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'identify', '--branch'])
            .add(ExpectShell.log('stdio', stdout='default'))
            .add(0),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'locate', 'set:added()'])
            .add(ExpectShell.log('stdio', stdout='foo\nbar/baz\n'))
            .add(1),
            Expect('rmdir', dict(dir=['wkdir/foo', 'wkdir/bar/baz'],
                                 logEnviron=True))
            .add(0),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'update', '--clean',
                                 '--rev', 'default'])
            .add(0),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'parents',
                                 '--template', '{node}\\n'])
            .add(ExpectShell.log('stdio', stdout='\n'))
            .add(ExpectShell.log('stdio', stdout='f6ad368298bd941e934a41f3babc827b2aa95a1d'))
            .add(0)
        )
        self.expectOutcome(result=SUCCESS)
        return self.runStep()

    def test_mode_incremental_existing_repo_added_files_old_rmdir(self):
        self.setupStep(
            mercurial.Mercurial(repourl='http://hg.mozilla.org',
                                mode='incremental', branchType='inrepo'))
        self.patch_workerVersionIsOlderThan(True)
        self.expectCommands(
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', '--version'])
            .add(0),
            Expect('stat', dict(file='wkdir/.buildbot-patched',
                                logEnviron=True))
            .add(1),
            Expect('stat', dict(file='wkdir/.hg',
                                logEnviron=True))
            .add(0),  # directory exists
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'pull',
                                 'http://hg.mozilla.org', '--rev', 'default'])
            .add(0),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'identify', '--branch'])
            .add(ExpectShell.log('stdio', stdout='default'))
            .add(0),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'locate', 'set:added()'])
            .add(ExpectShell.log('stdio', stdout='foo\nbar/baz\n'))
            .add(1),
            Expect('rmdir', dict(dir='wkdir/foo',
                                 logEnviron=True))
            .add(0),
            Expect('rmdir', dict(dir='wkdir/bar/baz',
                                 logEnviron=True))
            .add(0),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'update', '--clean',
                                 '--rev', 'default'])
            .add(0),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'parents',
                                 '--template', '{node}\\n'])
            .add(ExpectShell.log('stdio', stdout='\n'))
            .add(ExpectShell.log('stdio', stdout='f6ad368298bd941e934a41f3babc827b2aa95a1d'))
            .add(0)
        )
        self.expectOutcome(result=SUCCESS)
        return self.runStep()

    def test_mode_incremental_given_revision(self):
        self.setupStep(
            mercurial.Mercurial(repourl='http://hg.mozilla.org',
                                mode='incremental', branchType='inrepo'), dict(
                revision='abcdef01',
            ))

        self.expectCommands(
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', '--version'])
            .add(0),
            Expect('stat', dict(file='wkdir/.buildbot-patched',
                                logEnviron=True))
            .add(1),
            Expect('stat', dict(file='wkdir/.hg',
                                logEnviron=True))
            .add(0),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'pull',
                                 'http://hg.mozilla.org', '--rev', 'abcdef01'])
            .add(0),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'identify', '--branch'])
            .add(ExpectShell.log('stdio', stdout='default'))
            .add(0),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'locate', 'set:added()'])
            .add(1),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'update', '--clean',
                                 '--rev', 'abcdef01'])
            .add(0),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'parents',
                                 '--template', '{node}\\n'])
            .add(ExpectShell.log('stdio', stdout='\n'))
            .add(ExpectShell.log('stdio', stdout='f6ad368298bd941e934a41f3babc827b2aa95a1d'))
            .add(0)
        )
        self.expectOutcome(result=SUCCESS)
        return self.runStep()

    def test_mode_incremental_branch_change(self):
        self.setupStep(
            mercurial.Mercurial(repourl='http://hg.mozilla.org',
                                mode='incremental', branchType='inrepo'), dict(
                branch='stable',
            ))
        self.expectCommands(
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', '--version'])
            .add(0),
            Expect('stat', dict(file='wkdir/.buildbot-patched',
                                logEnviron=True))
            .add(1),
            Expect('stat', dict(file='wkdir/.hg',
                                logEnviron=True))
            .add(0),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'pull',
                                 'http://hg.mozilla.org', '--rev', 'stable'])
            .add(0),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'identify', '--branch'])
            .add(ExpectShell.log('stdio', stdout='default'))
            .add(0),
            Expect('rmdir', dict(dir='wkdir',
                                 logEnviron=True))
            .add(0),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'clone', '--noupdate',
                                 'http://hg.mozilla.org', '.'])
            .add(0),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'update',
                                 '--clean', '--rev', 'stable'])
            .add(0),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'parents',
                                 '--template', '{node}\\n'])
            .add(ExpectShell.log('stdio', stdout='\n'))
            .add(ExpectShell.log('stdio', stdout='f6ad368298bd941e934a41f3babc827b2aa95a1d'))
            .add(0)
        )
        self.expectOutcome(result=SUCCESS)
        return self.runStep()

    def test_mode_incremental_branch_change_no_clobberOnBranchChange(self):
        self.setupStep(
            mercurial.Mercurial(repourl='http://hg.mozilla.org',
                                mode='incremental', branchType='inrepo',
                                clobberOnBranchChange=False), dict(
                branch='stable',
            ))
        self.expectCommands(
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', '--version'])
            .add(0),
            Expect('stat', dict(file='wkdir/.buildbot-patched',
                                logEnviron=True))
            .add(1),
            Expect('stat', dict(file='wkdir/.hg',
                                logEnviron=True))
            .add(0),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'pull',
                                 'http://hg.mozilla.org', '--rev', 'stable'])
            .add(0),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'identify', '--branch'])
            .add(ExpectShell.log('stdio', stdout='default'))
            .add(0),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'locate', 'set:added()'])
            .add(1),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'update',
                                 '--clean', '--rev', 'stable'])
            .add(0),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'parents',
                                 '--template', '{node}\\n'])
            .add(ExpectShell.log('stdio', stdout='\n'))
            .add(ExpectShell.log('stdio', stdout='f6ad368298bd941e934a41f3babc827b2aa95a1d'))
            .add(0)
        )
        self.expectOutcome(result=SUCCESS)
        return self.runStep()

    def test_mode_full_clean_env(self):
        self.setupStep(
            mercurial.Mercurial(repourl='http://hg.mozilla.org',
                                mode='full', method='clean', branchType='inrepo',
                                env={'abc': '123'}))
        self.expectCommands(
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', '--version'], env={'abc': '123'})
            .add(0),
            Expect('stat', dict(file='wkdir/.buildbot-patched',
                                logEnviron=True))
            .add(1),
            Expect('stat', dict(file='wkdir/.hg',
                                logEnviron=True))
            .add(0),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', '--config',
                                 'extensions.purge=', 'purge'], env={'abc': '123'})
            .add(0),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'pull',
                                 'http://hg.mozilla.org', '--rev', 'default'], env={'abc': '123'})
            .add(0),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'identify', '--branch'],
                        env={'abc': '123'})
            .add(ExpectShell.log('stdio', stdout='default'))
            .add(0),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'locate', 'set:added()'],
                        env={'abc': '123'})
            .add(1),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'update', '--clean',
                                 '--rev', 'default'], env={'abc': '123'})
            .add(0),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'parents',
                                 '--template', '{node}\\n'], env={'abc': '123'})
            .add(ExpectShell.log('stdio', stdout='\n'))
            .add(ExpectShell.log('stdio', stdout='f6ad368298bd941e934a41f3babc827b2aa95a1d'))
            .add(0)
        )
        self.expectOutcome(result=SUCCESS)
        return self.runStep()

    def test_mode_full_clean_logEnviron(self):
        self.setupStep(
            mercurial.Mercurial(repourl='http://hg.mozilla.org',
                                mode='full', method='clean',
                                branchType='inrepo',
                                logEnviron=False))
        self.expectCommands(
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', '--version'],
                        logEnviron=False)
            .add(0),
            Expect('stat', dict(file='wkdir/.buildbot-patched',
                                logEnviron=False))
            .add(1),
            Expect('stat', dict(file='wkdir/.hg',
                                logEnviron=False))
            .add(0),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', '--config',
                                 'extensions.purge=', 'purge'],
                        logEnviron=False)
            .add(0),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'pull',
                                 'http://hg.mozilla.org', '--rev', 'default'],
                        logEnviron=False)
            .add(0),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'identify', '--branch'],
                        logEnviron=False)
            .add(ExpectShell.log('stdio', stdout='default'))
            .add(0),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'locate', 'set:added()'],
                        logEnviron=False)
            .add(1),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'update',
                                 '--clean', '--rev', 'default'],
                        logEnviron=False)
            .add(0),
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', 'parents',
                                 '--template', '{node}\\n'],
                        logEnviron=False)
            .add(ExpectShell.log('stdio', stdout='\n'))
            .add(ExpectShell.log('stdio', stdout='f6ad368298bd941e934a41f3babc827b2aa95a1d'))
            .add(0)
        )
        self.expectOutcome(result=SUCCESS)
        return self.runStep()

    def test_command_fails(self):
        self.setupStep(
            mercurial.Mercurial(repourl='http://hg.mozilla.org',
                                mode='full', method='fresh', branchType='inrepo'))
        self.expectCommands(
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', '--version'])
            .add(1)
        )
        self.expectOutcome(result=FAILURE)
        return self.runStep()

    def test_worker_connection_lost(self):
        self.setupStep(
            mercurial.Mercurial(repourl='http://hg.mozilla.org',
                                mode='full', method='clean', branchType='inrepo'))
        self.expectCommands(
            ExpectShell(workdir='wkdir',
                        command=['hg', '--verbose', '--version'])
            .add(('err', error.ConnectionLost()))
        )
        self.expectOutcome(result=RETRY, state_string="update (retry)")
        return self.runStep()
