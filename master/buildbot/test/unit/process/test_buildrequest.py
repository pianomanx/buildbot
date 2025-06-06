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

import datetime
import json
from unittest import mock

from twisted.internet import defer
from twisted.trial import unittest

from buildbot.process import buildrequest
from buildbot.process.builder import Builder
from buildbot.test import fakedb
from buildbot.test.fake import fakemaster
from buildbot.test.reactor import TestReactorMixin


class TestBuildRequestCollapser(TestReactorMixin, unittest.TestCase):
    @defer.inlineCallbacks
    def setUp(self):
        self.setup_test_reactor()
        self.master = yield fakemaster.make_master(self, wantData=True, wantDb=True)
        self.master.botmaster = mock.Mock(name='botmaster')
        self.master.botmaster.builders = {}
        self.builders = {}
        self.bldr = yield self.createBuilder('A', builderid=77)

    @defer.inlineCallbacks
    def createBuilder(self, name, builderid=None):
        if builderid is None:
            b = fakedb.Builder(name=name)
            yield self.master.db.insert_test_data([b])
            builderid = b.id

        bldr = mock.Mock(name=name)
        bldr.name = name
        bldr.master = self.master
        self.master.botmaster.builders[name] = bldr
        self.builders[name] = bldr
        bldr.getCollapseRequestsFn = lambda: False

        return bldr

    @defer.inlineCallbacks
    def do_request_collapse(self, brids, exp):
        brCollapser = buildrequest.BuildRequestCollapser(self.master, brids)
        self.assertEqual(exp, sorted((yield brCollapser.collapse())))

    @defer.inlineCallbacks
    def test_collapseRequests_no_other_request(self):
        def collapseRequests_fn(master, builder, brdict1, brdict2):
            # Allow all requests
            self.fail("Should never be called")
            # pylint: disable=unreachable
            return True

        self.bldr.getCollapseRequestsFn = lambda: collapseRequests_fn
        rows = [
            fakedb.Builder(id=77, name='A'),
            fakedb.SourceStamp(id=234, revision='r234', repository='repo', codebase='A'),
            fakedb.Change(changeid=14, codebase='A', sourcestampid=234),
            fakedb.Buildset(id=30, reason='foo', submitted_at=1300305712, results=-1),
            fakedb.BuildsetSourceStamp(sourcestampid=234, buildsetid=30),
            fakedb.BuildRequest(
                id=19, buildsetid=30, builderid=77, priority=13, submitted_at=1300305712, results=-1
            ),
        ]
        yield self.master.db.insert_test_data(rows)
        yield self.do_request_collapse([19], [])

    BASE_ROWS = [
        fakedb.Master(id=fakedb.FakeDBConnector.MASTER_ID),
        fakedb.Builder(id=77, name='A'),
        fakedb.SourceStamp(id=234, revision=None, repository='repo', codebase='C'),
        fakedb.Buildset(id=30, reason='foo', submitted_at=1300305712, results=-1),
        fakedb.BuildsetSourceStamp(sourcestampid=234, buildsetid=30),
        fakedb.Buildset(id=31, reason='foo', submitted_at=1300305712, results=-1),
        fakedb.BuildsetSourceStamp(sourcestampid=234, buildsetid=31),
        fakedb.Buildset(id=32, reason='foo', submitted_at=1300305712, results=-1),
        fakedb.BuildsetSourceStamp(sourcestampid=234, buildsetid=32),
        fakedb.BuildRequest(
            id=19, buildsetid=30, builderid=77, priority=13, submitted_at=1300305712, results=-1
        ),
        fakedb.BuildRequest(
            id=20, buildsetid=31, builderid=77, priority=13, submitted_at=1300305712, results=-1
        ),
        fakedb.BuildRequest(
            id=21, buildsetid=32, builderid=77, priority=13, submitted_at=1300305712, results=-1
        ),
    ]

    @defer.inlineCallbacks
    def test_collapseRequests_no_collapse(self):
        def collapseRequests_fn(master, builder, brdict1, brdict2):
            # Fail all collapse attempts
            return False

        self.bldr.getCollapseRequestsFn = lambda: collapseRequests_fn
        yield self.master.db.insert_test_data(self.BASE_ROWS)
        yield self.do_request_collapse([21], [])

    @defer.inlineCallbacks
    def test_collapseRequests_collapse_all(self):
        def collapseRequests_fn(master, builder, brdict1, brdict2):
            # collapse all attempts
            return True

        self.bldr.getCollapseRequestsFn = lambda: collapseRequests_fn
        yield self.master.db.insert_test_data(self.BASE_ROWS)
        yield self.do_request_collapse([21], [19, 20])

    @defer.inlineCallbacks
    def test_collapseRequests_collapse_all_duplicates(self):
        def collapseRequests_fn(master, builder, brdict1, brdict2):
            # collapse all attempts
            return True

        self.bldr.getCollapseRequestsFn = lambda: collapseRequests_fn
        yield self.master.db.insert_test_data(self.BASE_ROWS)
        yield self.do_request_collapse([21, 21], [19, 20])

    # As documented:
    # Sourcestamps are compatible if all of the below conditions are met:
    #
    # * Their codebase, branch, project, and repository attributes match exactly
    # * Neither source stamp has a patch (e.g., from a try scheduler)
    # * Either both source stamps are associated with changes, or neither are associated with
    #   changes but they have matching revisions.

    def makeBuildRequestRows(
        self,
        brid,
        bsid,
        changeid,
        ssid,
        patchid=None,
        bs_properties=None,
    ):
        rows = [
            fakedb.Buildset(id=bsid, reason='foo', submitted_at=1300305712, results=-1),
            fakedb.BuildsetSourceStamp(sourcestampid=ssid, buildsetid=bsid),
            fakedb.BuildRequest(
                id=brid,
                buildsetid=bsid,
                builderid=77,
                priority=13,
                submitted_at=1300305712,
                results=-1,
            ),
        ]
        if changeid:
            rows.append(
                fakedb.Change(
                    changeid=changeid,
                    branch='trunk',
                    revision='9283',
                    repository='svn://...',
                    project='world-domination',
                    sourcestampid=ssid,
                )
            )
        if patchid:
            rows.append(
                fakedb.Patch(
                    id=patchid,
                    patch_base64='aGVsbG8sIHdvcmxk',
                    patch_author='bar',
                    patch_comment='foo',
                    subdir='/foo',
                    patchlevel=3,
                )
            )
        if bs_properties:
            for prop_name, prop_value in bs_properties.items():
                rows.append(
                    fakedb.BuildsetProperty(
                        buildsetid=bsid,
                        property_name=prop_name,
                        property_value=json.dumps(prop_value),
                    ),
                )

        return rows

    @defer.inlineCallbacks
    def test_collapseRequests_collapse_default_with_codebases(self):
        rows = [
            fakedb.Master(id=fakedb.FakeDBConnector.MASTER_ID),
            fakedb.SourceStamp(id=222, codebase='A'),
            fakedb.SourceStamp(id=223, codebase='C'),
            fakedb.Builder(id=77, name='A'),
        ]
        rows += self.makeBuildRequestRows(22, 122, None, 222)
        rows += self.makeBuildRequestRows(21, 121, None, 223)
        rows += self.makeBuildRequestRows(19, 119, None, 223)
        rows += self.makeBuildRequestRows(20, 120, None, 223)
        self.bldr.getCollapseRequestsFn = lambda: Builder._defaultCollapseRequestFn
        yield self.master.db.insert_test_data(rows)
        yield self.do_request_collapse([22], [])
        yield self.do_request_collapse([21], [19, 20])

    @defer.inlineCallbacks
    def test_collapseRequests_collapse_default_does_not_collapse_older(self):
        rows = [
            fakedb.Master(id=fakedb.FakeDBConnector.MASTER_ID),
            fakedb.SourceStamp(id=222),
            fakedb.Builder(id=77, name='A'),
        ]
        rows += self.makeBuildRequestRows(21, 121, None, 222)
        rows += self.makeBuildRequestRows(19, 119, None, 222)
        rows += self.makeBuildRequestRows(20, 120, None, 222)
        self.bldr.getCollapseRequestsFn = lambda: Builder._defaultCollapseRequestFn
        yield self.master.db.insert_test_data(rows)
        yield self.do_request_collapse([19], [])
        yield self.do_request_collapse([20], [19])
        yield self.do_request_collapse([21], [20])

    @defer.inlineCallbacks
    def test_collapseRequests_collapse_default_does_not_collapse_concurrent_claims(self):
        rows = [
            fakedb.Master(id=fakedb.FakeDBConnector.MASTER_ID),
            fakedb.SourceStamp(id=222),
            fakedb.Builder(id=77, name='A'),
        ]
        rows += self.makeBuildRequestRows(21, 121, None, 222)
        rows += self.makeBuildRequestRows(19, 119, None, 222)
        rows += self.makeBuildRequestRows(20, 120, None, 222)

        claimed = []

        @defer.inlineCallbacks
        def collapse_fn(master, builder, brdict1, brdict2):
            if not claimed:
                yield self.master.data.updates.claimBuildRequests([20])
                claimed.append(20)
            res = yield Builder._defaultCollapseRequestFn(master, builder, brdict1, brdict2)
            return res

        self.bldr.getCollapseRequestsFn = lambda: collapse_fn

        yield self.master.db.insert_test_data(rows)
        yield self.do_request_collapse([21], [19])

    @defer.inlineCallbacks
    def test_collapseRequests_collapse_default_does_not_collapse_scheduler_props(self):
        rows = [
            fakedb.Master(id=fakedb.FakeDBConnector.MASTER_ID),
            fakedb.SourceStamp(id=222),
            fakedb.Builder(id=77, name='A'),
        ]
        rows += self.makeBuildRequestRows(
            21, 121, None, 222, bs_properties={'prop': ('value', 'Scheduler')}
        )
        rows += self.makeBuildRequestRows(
            20, 120, None, 222, bs_properties={'prop': ('value', 'Other source')}
        )
        rows += self.makeBuildRequestRows(
            19, 119, None, 222, bs_properties={'prop': ('value2', 'Scheduler')}
        )
        rows += self.makeBuildRequestRows(
            18, 118, None, 222, bs_properties={'prop': ('value', 'Scheduler')}
        )
        rows += self.makeBuildRequestRows(
            17, 117, None, 222, bs_properties={'prop': ('value3', 'Other source')}
        )
        rows += self.makeBuildRequestRows(16, 116, None, 222)

        self.bldr.getCollapseRequestsFn = lambda: Builder._defaultCollapseRequestFn

        yield self.master.db.insert_test_data(rows)
        # only the same property coming from a scheduler is matched
        yield self.do_request_collapse([21], [18])
        # only takes into account properties coming from scheduler
        yield self.do_request_collapse([20], [16, 17])

    @defer.inlineCallbacks
    def test_collapseRequests_collapse_default_with_codebases_branches(self):
        rows = [
            fakedb.Master(id=fakedb.FakeDBConnector.MASTER_ID),
            fakedb.SourceStamp(id=222, codebase='A', branch='br1'),
            fakedb.SourceStamp(id=223, codebase='C', branch='br2'),
            fakedb.SourceStamp(id=224, codebase='C', branch='br3'),
            fakedb.Builder(id=77, name='A'),
        ]
        rows += self.makeBuildRequestRows(22, 122, None, 222)
        rows += self.makeBuildRequestRows(21, 121, None, 223)
        rows += self.makeBuildRequestRows(19, 119, None, 223)
        rows += self.makeBuildRequestRows(20, 120, None, 224)
        self.bldr.getCollapseRequestsFn = lambda: Builder._defaultCollapseRequestFn

        yield self.master.db.insert_test_data(rows)
        yield self.do_request_collapse([22], [])
        yield self.do_request_collapse([21], [19])

    @defer.inlineCallbacks
    def test_collapseRequests_collapse_default_with_codebases_repository(self):
        rows = [
            fakedb.Master(id=fakedb.FakeDBConnector.MASTER_ID),
            fakedb.SourceStamp(id=222, codebase='A', repository='repo1'),
            fakedb.SourceStamp(id=223, codebase='C', repository='repo2'),
            fakedb.SourceStamp(id=224, codebase='C', repository='repo3'),
            fakedb.Builder(id=77, name='A'),
        ]
        rows += self.makeBuildRequestRows(22, 122, None, 222)
        rows += self.makeBuildRequestRows(21, 121, None, 223)
        rows += self.makeBuildRequestRows(19, 119, None, 223)
        rows += self.makeBuildRequestRows(20, 120, None, 224)
        self.bldr.getCollapseRequestsFn = lambda: Builder._defaultCollapseRequestFn

        yield self.master.db.insert_test_data(rows)
        yield self.do_request_collapse([22], [])
        yield self.do_request_collapse([21], [19])

    @defer.inlineCallbacks
    def test_collapseRequests_collapse_default_with_codebases_projects(self):
        rows = [
            fakedb.Master(id=fakedb.FakeDBConnector.MASTER_ID),
            fakedb.SourceStamp(id=222, codebase='A', project='proj1'),
            fakedb.SourceStamp(id=223, codebase='C', project='proj2'),
            fakedb.SourceStamp(id=224, codebase='C', project='proj3'),
            fakedb.Builder(id=77, name='A'),
        ]
        rows += self.makeBuildRequestRows(22, 122, None, 222)
        rows += self.makeBuildRequestRows(21, 121, None, 223)
        rows += self.makeBuildRequestRows(19, 119, None, 223)
        rows += self.makeBuildRequestRows(20, 120, None, 224)
        self.bldr.getCollapseRequestsFn = lambda: Builder._defaultCollapseRequestFn

        yield self.master.db.insert_test_data(rows)
        yield self.do_request_collapse([22], [])
        yield self.do_request_collapse([21], [19])

    # * Neither source stamp has a patch (e.g., from a try scheduler)
    @defer.inlineCallbacks
    def test_collapseRequests_collapse_default_with_a_patch(self):
        rows = [
            fakedb.Master(id=fakedb.FakeDBConnector.MASTER_ID),
            fakedb.SourceStamp(id=222, codebase='A'),
            fakedb.SourceStamp(id=223, codebase='C'),
            fakedb.Patch(
                id=123,
                patch_base64='aGVsbG8sIHdvcmxk',
                patch_author='bar',
                patch_comment='foo',
                subdir='/foo',
                patchlevel=3,
            ),
            fakedb.SourceStamp(id=224, codebase='C', patchid=123),
            fakedb.Builder(id=77, name='A'),
        ]
        rows += self.makeBuildRequestRows(22, 122, None, 222)
        rows += self.makeBuildRequestRows(21, 121, None, 223)
        rows += self.makeBuildRequestRows(19, 119, None, 224)
        rows += self.makeBuildRequestRows(20, 120, None, 223)
        self.bldr.getCollapseRequestsFn = lambda: Builder._defaultCollapseRequestFn
        yield self.master.db.insert_test_data(rows)
        yield self.do_request_collapse([22], [])
        yield self.do_request_collapse([21], [20])

    # * Either both source stamps are associated with changes..
    @defer.inlineCallbacks
    def test_collapseRequests_collapse_default_with_changes(self):
        rows = [
            fakedb.Master(id=fakedb.FakeDBConnector.MASTER_ID),
            fakedb.SourceStamp(id=222, codebase='A'),
            fakedb.SourceStamp(id=223, codebase='C'),
            fakedb.Builder(id=77, name='A'),
        ]
        rows += self.makeBuildRequestRows(22, 122, None, 222)
        rows += self.makeBuildRequestRows(21, 121, 123, 223)
        rows += self.makeBuildRequestRows(19, 119, None, 223)
        rows += self.makeBuildRequestRows(20, 120, 124, 223)
        self.bldr.getCollapseRequestsFn = lambda: Builder._defaultCollapseRequestFn
        yield self.master.db.insert_test_data(rows)
        yield self.do_request_collapse([22], [])
        yield self.do_request_collapse([21], [19, 20])

    # * ... or neither are associated with changes but they have matching revisions.
    @defer.inlineCallbacks
    def test_collapseRequests_collapse_default_with_non_matching_revision(self):
        rows = [
            fakedb.Master(id=fakedb.FakeDBConnector.MASTER_ID),
            fakedb.SourceStamp(id=222, codebase='A'),
            fakedb.SourceStamp(id=223, codebase='C'),
            fakedb.SourceStamp(id=224, codebase='C', revision='abcd1234'),
            fakedb.Builder(id=77, name='A'),
        ]
        rows += self.makeBuildRequestRows(22, 122, None, 222)
        rows += self.makeBuildRequestRows(21, 121, None, 223)
        rows += self.makeBuildRequestRows(19, 119, None, 224)
        rows += self.makeBuildRequestRows(20, 120, None, 223)
        self.bldr.getCollapseRequestsFn = lambda: Builder._defaultCollapseRequestFn
        yield self.master.db.insert_test_data(rows)
        yield self.do_request_collapse([22], [])
        yield self.do_request_collapse([21], [20])


class TestSourceStamp(unittest.TestCase):
    def test_asdict_minimal(self):
        ssdatadict = {
            'ssid': '123',
            'branch': None,
            'revision': None,
            'patch': None,
            'repository': 'testrepo',
            'codebase': 'testcodebase',
            'project': 'testproject',
            'created_at': datetime.datetime(2019, 4, 1, 23, 38, 33, 154354),
        }
        ss = buildrequest.TempSourceStamp(ssdatadict)

        self.assertEqual(
            ss.asDict(),
            {
                'branch': None,
                'codebase': 'testcodebase',
                'patch_author': None,
                'patch_body': None,
                'patch_comment': None,
                'patch_level': None,
                'patch_subdir': None,
                'project': 'testproject',
                'repository': 'testrepo',
                'revision': None,
            },
        )

    def test_asdict_no_patch(self):
        ssdatadict = {
            'ssid': '123',
            'branch': 'testbranch',
            'revision': 'testrev',
            'patch': None,
            'repository': 'testrepo',
            'codebase': 'testcodebase',
            'project': 'testproject',
            'created_at': datetime.datetime(2019, 4, 1, 23, 38, 33, 154354),
        }
        ss = buildrequest.TempSourceStamp(ssdatadict)

        self.assertEqual(
            ss.asDict(),
            {
                'branch': 'testbranch',
                'codebase': 'testcodebase',
                'patch_author': None,
                'patch_body': None,
                'patch_comment': None,
                'patch_level': None,
                'patch_subdir': None,
                'project': 'testproject',
                'repository': 'testrepo',
                'revision': 'testrev',
            },
        )

    def test_asdict_with_patch(self):
        ssdatadict = {
            'ssid': '123',
            'branch': 'testbranch',
            'revision': 'testrev',
            'patch': {
                'patchid': 1234,
                'body': b'testbody',
                'level': 2,
                'author': 'testauthor',
                'comment': 'testcomment',
                'subdir': 'testsubdir',
            },
            'repository': 'testrepo',
            'codebase': 'testcodebase',
            'project': 'testproject',
            'created_at': datetime.datetime(2019, 4, 1, 23, 38, 33, 154354),
        }
        ss = buildrequest.TempSourceStamp(ssdatadict)

        self.assertEqual(
            ss.asDict(),
            {
                'branch': 'testbranch',
                'codebase': 'testcodebase',
                'patch_author': 'testauthor',
                'patch_body': b'testbody',
                'patch_comment': 'testcomment',
                'patch_level': 2,
                'patch_subdir': 'testsubdir',
                'project': 'testproject',
                'repository': 'testrepo',
                'revision': 'testrev',
            },
        )


class TestBuildRequest(TestReactorMixin, unittest.TestCase):
    def setUp(self):
        self.setup_test_reactor()

    @defer.inlineCallbacks
    def test_fromBrdict(self):
        master = yield fakemaster.make_master(self, wantData=True, wantDb=True)
        yield master.db.insert_test_data([
            fakedb.Master(id=fakedb.FakeDBConnector.MASTER_ID),
            fakedb.Builder(id=77, name='bldr'),
            fakedb.SourceStamp(
                id=234,
                branch='trunk',
                revision='9284',
                repository='svn://...',
                project='world-domination',
            ),
            fakedb.Change(
                changeid=13,
                branch='trunk',
                revision='9283',
                repository='svn://...',
                project='world-domination',
                sourcestampid=234,
            ),
            fakedb.Buildset(id=539, reason='triggered'),
            fakedb.BuildsetSourceStamp(buildsetid=539, sourcestampid=234),
            fakedb.BuildsetProperty(buildsetid=539, property_name='x', property_value='[1, "X"]'),
            fakedb.BuildsetProperty(buildsetid=539, property_name='y', property_value='[2, "Y"]'),
            fakedb.BuildRequest(
                id=288, buildsetid=539, builderid=77, priority=13, submitted_at=1200000000
            ),
        ])
        # use getBuildRequest to minimize the risk from changes to the format
        # of the brdict
        brdict = yield master.db.buildrequests.getBuildRequest(288)
        br = yield buildrequest.BuildRequest.fromBrdict(master, brdict)

        # check enough of the source stamp to verify it found the changes
        self.assertEqual([ss.ssid for ss in br.sources.values()], [234])

        self.assertEqual(br.reason, 'triggered')

        self.assertEqual(br.properties.getProperty('x'), 1)
        self.assertEqual(br.properties.getProperty('y'), 2)
        self.assertEqual(br.submitted_at, 1200000000)
        self.assertEqual(br.buildername, 'bldr')
        self.assertEqual(br.priority, 13)
        self.assertEqual(br.id, 288)
        self.assertEqual(br.bsid, 539)

    @defer.inlineCallbacks
    def test_fromBrdict_no_sourcestamps(self):
        master = yield fakemaster.make_master(self, wantData=True, wantDb=True)
        yield master.db.insert_test_data([
            fakedb.Master(id=fakedb.FakeDBConnector.MASTER_ID),
            fakedb.Builder(id=78, name='not important'),
            fakedb.Buildset(id=539, reason='triggered'),
            # buildset has no sourcestamps
            fakedb.BuildRequest(id=288, buildsetid=539, builderid=78, priority=0),
        ])
        # use getBuildRequest to minimize the risk from changes to the format
        # of the brdict
        brdict = yield master.db.buildrequests.getBuildRequest(288)
        with self.assertRaises(AssertionError):
            yield buildrequest.BuildRequest.fromBrdict(master, brdict)

    @defer.inlineCallbacks
    def test_fromBrdict_multiple_sourcestamps(self):
        master = yield fakemaster.make_master(self, wantData=True, wantDb=True)
        yield master.db.insert_test_data([
            fakedb.Master(id=fakedb.FakeDBConnector.MASTER_ID),
            fakedb.Builder(id=77, name='bldr'),
            fakedb.SourceStamp(
                id=234,
                branch='trunk',
                revision='9283',
                repository='svn://a..',
                codebase='A',
                project='world-domination',
            ),
            fakedb.Change(
                changeid=13,
                branch='trunk',
                revision='9283',
                repository='svn://a..',
                codebase='A',
                project='world-domination',
                sourcestampid=234,
            ),
            fakedb.SourceStamp(
                id=235,
                branch='trunk',
                revision='9284',
                repository='svn://b..',
                codebase='B',
                project='world-domination',
            ),
            fakedb.Change(
                changeid=14,
                branch='trunk',
                revision='9284',
                repository='svn://b..',
                codebase='B',
                project='world-domination',
                sourcestampid=235,
            ),
            fakedb.Buildset(id=539, reason='triggered'),
            fakedb.BuildsetSourceStamp(buildsetid=539, sourcestampid=234),
            fakedb.BuildsetProperty(buildsetid=539, property_name='x', property_value='[1, "X"]'),
            fakedb.BuildsetProperty(buildsetid=539, property_name='y', property_value='[2, "Y"]'),
            fakedb.BuildRequest(
                id=288, buildsetid=539, builderid=77, priority=13, submitted_at=1200000000
            ),
        ])
        # use getBuildRequest to minimize the risk from changes to the format
        # of the brdict
        brdict = yield master.db.buildrequests.getBuildRequest(288)
        br = yield buildrequest.BuildRequest.fromBrdict(master, brdict)

        self.assertEqual(br.reason, 'triggered')

        self.assertEqual(br.properties.getProperty('x'), 1)
        self.assertEqual(br.properties.getProperty('y'), 2)
        self.assertEqual(br.submitted_at, 1200000000)
        self.assertEqual(br.buildername, 'bldr')
        self.assertEqual(br.priority, 13)
        self.assertEqual(br.id, 288)
        self.assertEqual(br.bsid, 539)

    @defer.inlineCallbacks
    def test_mergeSourceStampsWith_common_codebases(self):
        """This testcase has two buildrequests
        Request Change Codebase Revision Comment
        ----------------------------------------------------------------------
        288     13     A        9283
        289     15     A        9284
        288     14     B        9200
        289     16     B        9201
        --------------------------------
        After merged in Build:
        Source1 has rev 9284 and contains changes 13 and 15 from repository svn://a
        Source2 has rev 9201 and contains changes 14 and 16 from repository svn://b
        """
        brs = []  # list of buildrequests
        master = yield fakemaster.make_master(self, wantData=True, wantDb=True)
        yield master.db.insert_test_data([
            fakedb.Master(id=fakedb.FakeDBConnector.MASTER_ID),
            fakedb.Builder(id=77, name='bldr'),
            fakedb.SourceStamp(
                id=234,
                branch='trunk',
                revision='9283',
                repository='svn://a..',
                codebase='A',
                project='world-domination',
            ),
            fakedb.Change(
                changeid=13,
                branch='trunk',
                revision='9283',
                repository='svn://a..',
                codebase='A',
                project='world-domination',
                sourcestampid=234,
            ),
            fakedb.SourceStamp(
                id=235,
                branch='trunk',
                revision='9200',
                repository='svn://b..',
                codebase='B',
                project='world-domination',
            ),
            fakedb.Change(
                changeid=14,
                branch='trunk',
                revision='9200',
                repository='svn://b..',
                codebase='A',
                project='world-domination',
                sourcestampid=235,
            ),
            fakedb.SourceStamp(
                id=236,
                branch='trunk',
                revision='9284',
                repository='svn://a..',
                codebase='A',
                project='world-domination',
            ),
            fakedb.Change(
                changeid=15,
                branch='trunk',
                revision='9284',
                repository='svn://a..',
                codebase='A',
                project='world-domination',
                sourcestampid=236,
            ),
            fakedb.SourceStamp(
                id=237,
                branch='trunk',
                revision='9201',
                repository='svn://b..',
                codebase='B',
                project='world-domination',
            ),
            fakedb.Change(
                changeid=16,
                branch='trunk',
                revision='9201',
                repository='svn://b..',
                codebase='B',
                project='world-domination',
                sourcestampid=237,
            ),
            fakedb.Buildset(id=539, reason='triggered'),
            fakedb.BuildsetSourceStamp(buildsetid=539, sourcestampid=234),
            fakedb.BuildsetSourceStamp(buildsetid=539, sourcestampid=235),
            fakedb.BuildRequest(id=288, buildsetid=539, builderid=77),
            fakedb.Buildset(id=540, reason='triggered'),
            fakedb.BuildsetSourceStamp(buildsetid=540, sourcestampid=236),
            fakedb.BuildsetSourceStamp(buildsetid=540, sourcestampid=237),
            fakedb.BuildRequest(id=289, buildsetid=540, builderid=77),
        ])
        # use getBuildRequest to minimize the risk from changes to the format
        # of the brdict
        brdict = yield master.db.buildrequests.getBuildRequest(288)
        res = yield buildrequest.BuildRequest.fromBrdict(master, brdict)
        brs.append(res)
        brdict = yield master.db.buildrequests.getBuildRequest(289)
        res = yield buildrequest.BuildRequest.fromBrdict(master, brdict)
        brs.append(res)

        sources = brs[0].mergeSourceStampsWith(brs[1:])

        source1 = source2 = None
        for source in sources:
            if source.codebase == 'A':
                source1 = source
            if source.codebase == 'B':
                source2 = source

        self.assertFalse(source1 is None)
        self.assertEqual(source1.revision, '9284')

        self.assertFalse(source2 is None)
        self.assertEqual(source2.revision, '9201')

    @defer.inlineCallbacks
    def test_canBeCollapsed_different_codebases_raises_error(self):
        """This testcase has two buildrequests
        Request Change Codebase   Revision Comment
        ----------------------------------------------------------------------
        288     17     C          1800     request 1 has repo not in request 2
        289     18     D          2100     request 2 has repo not in request 1
        --------------------------------
        Merge cannot be performed and raises error:
          Merging requests requires both requests to have the same codebases
        """
        master = yield fakemaster.make_master(self, wantData=True, wantDb=True)
        yield master.db.insert_test_data([
            fakedb.Master(id=fakedb.FakeDBConnector.MASTER_ID),
            fakedb.Builder(id=77, name='bldr'),
            fakedb.SourceStamp(
                id=238,
                branch='trunk',
                revision='1800',
                repository='svn://c..',
                codebase='C',
                project='world-domination',
            ),
            fakedb.Change(
                changeid=17,
                branch='trunk',
                revision='1800',
                repository='svn://c..',
                codebase='C',
                project='world-domination',
                sourcestampid=238,
            ),
            fakedb.SourceStamp(
                id=239,
                branch='trunk',
                revision='2100',
                repository='svn://d..',
                codebase='D',
                project='world-domination',
            ),
            fakedb.Change(
                changeid=18,
                branch='trunk',
                revision='2100',
                repository='svn://d..',
                codebase='D',
                project='world-domination',
                sourcestampid=239,
            ),
            fakedb.Buildset(id=539, reason='triggered'),
            fakedb.BuildsetSourceStamp(buildsetid=539, sourcestampid=238),
            fakedb.BuildRequest(id=288, buildsetid=539, builderid=77),
            fakedb.Buildset(id=540, reason='triggered'),
            fakedb.BuildsetSourceStamp(buildsetid=540, sourcestampid=239),
            fakedb.BuildRequest(id=289, buildsetid=540, builderid=77),
        ])
        old_br = yield master.data.get(('buildrequests', 288))
        new_br = yield master.data.get(('buildrequests', 289))
        can_collapse = yield buildrequest.BuildRequest.canBeCollapsed(master, new_br, old_br)

        self.assertEqual(can_collapse, False)
