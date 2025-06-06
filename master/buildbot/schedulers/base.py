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
from typing import ClassVar

from twisted.internet import defer
from twisted.python import log
from zope.interface import implementer

from buildbot import config
from buildbot import interfaces
from buildbot.changes import changes
from buildbot.process.properties import Properties
from buildbot.util.service import ClusteredBuildbotService
from buildbot.util.state import StateMixin
from buildbot.warnings import warn_deprecated

if TYPE_CHECKING:
    from collections.abc import Sequence


@implementer(interfaces.IScheduler)
class BaseScheduler(ClusteredBuildbotService, StateMixin):
    DEFAULT_CODEBASES: dict[str, dict[str, str]] = {'': {}}

    compare_attrs: ClassVar[Sequence[str]] = (
        *ClusteredBuildbotService.compare_attrs,
        'builderNames',
        'properties',
        'codebases',
    )

    def __init__(self, name, builderNames, properties=None, codebases=None, priority=None):
        warn_deprecated(
            '4.3.0',
            'BaseScheduler has been deprecated, use ReconfigurableBaseScheduler',
        )

        super().__init__(name=name)
        if codebases is None:
            codebases = self.DEFAULT_CODEBASES.copy()

        ok = True
        if interfaces.IRenderable.providedBy(builderNames):
            pass
        elif isinstance(builderNames, (list, tuple)):
            for b in builderNames:
                if not isinstance(b, str) and not interfaces.IRenderable.providedBy(b):
                    ok = False
        else:
            ok = False
        if not ok:
            config.error(
                "The builderNames argument to a scheduler must be a list "
                "of Builder names or an IRenderable object that will render"
                "to a list of builder names."
            )

        self.builderNames = builderNames

        if properties is None:
            properties = {}
        self.properties = Properties()
        self.properties.update(properties, "Scheduler")
        self.properties.setProperty("scheduler", name, "Scheduler")
        self.objectid = None

        # Set the codebases that are necessary to process the changes
        # These codebases will always result in a sourcestamp with or without
        # changes
        known_keys = set(['branch', 'repository', 'revision'])
        if codebases is None:
            config.error("Codebases cannot be None")
        elif isinstance(codebases, list):
            codebases = dict((codebase, {}) for codebase in codebases)
        elif not isinstance(codebases, dict):
            config.error("Codebases must be a dict of dicts, or list of strings")
        else:
            for codebase, attrs in codebases.items():
                if not isinstance(attrs, dict):
                    config.error("Codebases must be a dict of dicts")
                else:
                    unk = set(attrs) - known_keys
                    if unk:
                        config.error(
                            f"Unknown codebase keys {', '.join(unk)} for codebase {codebase}"
                        )

        self.codebases = codebases

        # internal variables
        self._change_consumer = None
        self._enable_consumer = None
        self._change_consumption_lock = defer.DeferredLock()

        self.enabled = True
        if priority and not isinstance(priority, int) and not callable(priority):
            config.error(
                f"Invalid type for priority: {type(priority)}. "
                "It must either be an integer or a function"
            )
        self.priority = priority

    def __repr__(self):
        """
        Provide a meaningful string representation of scheduler.
        """
        return (
            f'<{self.__class__.__name__}({self.name}, {self.builderNames}, enabled={self.enabled})>'
        )

    def reconfigService(self, *args, **kwargs):
        raise NotImplementedError()

    # activity handling
    @defer.inlineCallbacks
    def activate(self):
        if not self.enabled:
            return None

        # even if we aren't called via _activityPoll(), at this point we
        # need to ensure the service id is set correctly
        if self.serviceid is None:
            self.serviceid = yield self._getServiceId()
            assert self.serviceid is not None

        schedulerData = yield self._getScheduler(self.serviceid)

        if schedulerData:
            self.enabled = schedulerData.enabled

        if not self._enable_consumer:
            yield self.startConsumingEnableEvents()
        return None

    @defer.inlineCallbacks
    def _enabledCallback(self, key, msg):
        if msg['enabled']:
            self.enabled = True
            yield self.activate()
        else:
            yield self.deactivate()
            self.enabled = False

    @defer.inlineCallbacks
    def deactivate(self):
        if not self.enabled:
            return None
        yield self._stopConsumingChanges()
        return None

    # service handling

    def _getServiceId(self):
        return self.master.data.updates.findSchedulerId(self.name)

    def _getScheduler(self, sid):
        return self.master.db.schedulers.getScheduler(sid)

    def _claimService(self):
        return self.master.data.updates.trySetSchedulerMaster(self.serviceid, self.master.masterid)

    def _unclaimService(self):
        return self.master.data.updates.trySetSchedulerMaster(self.serviceid, None)

    # status queries

    # deprecated: these aren't compatible with distributed schedulers

    def listBuilderNames(self):
        return self.builderNames

    # change handling

    @defer.inlineCallbacks
    def startConsumingChanges(self, fileIsImportant=None, change_filter=None, onlyImportant=False):
        assert fileIsImportant is None or callable(fileIsImportant)

        # register for changes with the data API
        assert not self._change_consumer
        self._change_consumer = yield self.master.mq.startConsuming(
            lambda k, m: self._changeCallback(k, m, fileIsImportant, change_filter, onlyImportant),
            ('changes', None, 'new'),
        )

    @defer.inlineCallbacks
    def startConsumingEnableEvents(self):
        assert not self._enable_consumer
        self._enable_consumer = yield self.master.mq.startConsuming(
            self._enabledCallback, ('schedulers', str(self.serviceid), 'updated')
        )

    @defer.inlineCallbacks
    def _changeCallback(self, key, msg, fileIsImportant, change_filter, onlyImportant):
        # ignore changes delivered while we're not running
        if not self._change_consumer:
            return

        # get a change object, since the API requires it
        chdict = yield self.master.db.changes.getChange(msg['changeid'])
        change = yield changes.Change.fromChdict(self.master, chdict)

        # filter it
        if change_filter and not change_filter.filter_change(change):
            return

        if change.codebase not in self.codebases:
            log.msg(
                format='change contains codebase %(codebase)s that is '
                'not processed by scheduler %(name)s',
                codebase=change.codebase,
                name=self.name,
            )
            return

        if fileIsImportant:
            try:
                important = fileIsImportant(change)
                if not important and onlyImportant:
                    return
            except Exception as e:
                log.err(e, f'in fileIsImportant check for {change}')
                return
        else:
            important = True

        # use change_consumption_lock to ensure the service does not stop
        # while this change is being processed
        d = self._change_consumption_lock.run(self.gotChange, change, important)
        d.addErrback(log.err, 'while processing change')

    def _stopConsumingChanges(self):
        # (note: called automatically in deactivate)

        # acquire the lock change consumption lock to ensure that any change
        # consumption is complete before we are done stopping consumption
        def stop():
            if self._change_consumer:
                self._change_consumer.stopConsuming()
                self._change_consumer = None

        return self._change_consumption_lock.run(stop)

    def gotChange(self, change, important):
        raise NotImplementedError

    # starting builds

    @defer.inlineCallbacks
    def addBuildsetForSourceStampsWithDefaults(
        self,
        reason,
        sourcestamps=None,
        waited_for=False,
        properties=None,
        builderNames=None,
        priority=None,
        **kw,
    ):
        if sourcestamps is None:
            sourcestamps = []

        # convert sourcestamps to a dictionary keyed by codebase
        stampsByCodebase = {}
        for ss in sourcestamps:
            cb = ss['codebase']
            if cb in stampsByCodebase:
                raise RuntimeError("multiple sourcestamps with same codebase")
            stampsByCodebase[cb] = ss

        # Merge codebases with the passed list of sourcestamps
        # This results in a new sourcestamp for each codebase
        stampsWithDefaults = []
        for codebase in self.codebases:
            cb = yield self.getCodebaseDict(codebase)
            ss = {
                'codebase': codebase,
                'repository': cb.get('repository', ''),
                'branch': cb.get('branch', None),
                'revision': cb.get('revision', None),
                'project': '',
            }
            # apply info from passed sourcestamps onto the configured default
            # sourcestamp attributes for this codebase.
            ss.update(stampsByCodebase.get(codebase, {}))
            stampsWithDefaults.append(ss)

        # fill in any supplied sourcestamps that aren't for a codebase in the
        # scheduler's codebase dictionary
        for codebase in set(stampsByCodebase) - set(self.codebases):
            cb = stampsByCodebase[codebase]
            ss = {
                'codebase': codebase,
                'repository': cb.get('repository', ''),
                'branch': cb.get('branch', None),
                'revision': cb.get('revision', None),
                'project': '',
            }
            stampsWithDefaults.append(ss)

        rv = yield self.addBuildsetForSourceStamps(
            sourcestamps=stampsWithDefaults,
            reason=reason,
            waited_for=waited_for,
            properties=properties,
            builderNames=builderNames,
            priority=priority,
            **kw,
        )
        return rv

    def getCodebaseDict(self, codebase):
        # Hook for subclasses to change codebase parameters when a codebase does
        # not have a change associated with it.
        try:
            return defer.succeed(self.codebases[codebase])
        except KeyError:
            return defer.fail()

    @defer.inlineCallbacks
    def addBuildsetForChanges(
        self,
        waited_for=False,
        reason='',
        external_idstring=None,
        changeids=None,
        builderNames=None,
        properties=None,
        priority=None,
        **kw,
    ):
        if changeids is None:
            changeids = []
        changesByCodebase = {}

        def get_last_change_for_codebase(codebase):
            return max(changesByCodebase[codebase], key=lambda change: change.changeid)

        # Changes are retrieved from database and grouped by their codebase
        for changeid in changeids:
            chdict = yield self.master.db.changes.getChange(changeid)
            changesByCodebase.setdefault(chdict.codebase, []).append(chdict)

        sourcestamps = []
        for codebase in sorted(self.codebases):
            if codebase not in changesByCodebase:
                # codebase has no changes
                # create a sourcestamp that has no changes
                cb = yield self.getCodebaseDict(codebase)

                ss = {
                    'codebase': codebase,
                    'repository': cb.get('repository', ''),
                    'branch': cb.get('branch', None),
                    'revision': cb.get('revision', None),
                    'project': '',
                }
            else:
                lastChange = get_last_change_for_codebase(codebase)
                ss = lastChange.sourcestampid
            sourcestamps.append(ss)

        if priority is None:
            priority = self.priority

        if callable(priority):
            priority = priority(builderNames or self.builderNames, changesByCodebase)
        elif priority is None:
            priority = 0

        # add one buildset, using the calculated sourcestamps
        bsid, brids = yield self.addBuildsetForSourceStamps(
            waited_for,
            sourcestamps=sourcestamps,
            reason=reason,
            external_idstring=external_idstring,
            builderNames=builderNames,
            properties=properties,
            priority=priority,
            **kw,
        )

        return (bsid, brids)

    @defer.inlineCallbacks
    def addBuildsetForSourceStamps(
        self,
        waited_for=False,
        sourcestamps=None,
        reason='',
        external_idstring=None,
        properties=None,
        builderNames=None,
        priority=None,
        **kw,
    ):
        if sourcestamps is None:
            sourcestamps = []
        # combine properties
        if properties:
            properties.updateFromProperties(self.properties)
        else:
            properties = self.properties

        # make a fresh copy that we actually can modify safely
        properties = Properties.fromDict(properties.asDict())

        # make extra info available from properties.render()
        properties.master = self.master
        properties.sourcestamps = []
        properties.changes = []
        for ss in sourcestamps:
            if isinstance(ss, int):
                # fetch actual sourcestamp and changes from data API
                properties.sourcestamps.append((yield self.master.data.get(('sourcestamps', ss))))
                properties.changes.extend(
                    (yield self.master.data.get(('sourcestamps', ss, 'changes')))
                )
            else:
                # sourcestamp with no change, see addBuildsetForChanges
                properties.sourcestamps.append(ss)

        for c in properties.changes:
            properties.updateFromProperties(Properties.fromDict(c['properties']))

        # apply the default builderNames
        if not builderNames:
            builderNames = self.builderNames

        # dynamically get the builder list to schedule
        builderNames = yield properties.render(builderNames)

        # Get the builder ids
        # Note that there is a data.updates.findBuilderId(name)
        # but that would merely only optimize the single builder case, while
        # probably the multiple builder case will be severely impacted by the
        # several db requests needed.
        builderids = []
        for bldr in (yield self.master.data.get(('builders',))):
            if bldr['name'] in builderNames:
                builderids.append(bldr['builderid'])

        # translate properties object into a dict as required by the
        # addBuildset method
        properties_dict = yield properties.render(properties.asDict())

        if priority is None:
            priority = 0

        bsid, brids = yield self.master.data.updates.addBuildset(
            scheduler=self.name,
            sourcestamps=sourcestamps,
            reason=reason,
            waited_for=waited_for,
            properties=properties_dict,
            builderids=builderids,
            external_idstring=external_idstring,
            priority=priority,
            **kw,
        )
        return (bsid, brids)


@implementer(interfaces.IScheduler)
class ReconfigurableBaseScheduler(ClusteredBuildbotService, StateMixin):
    DEFAULT_CODEBASES: dict[str, dict[str, str]] = {'': {}}

    compare_attrs: ClassVar[Sequence[str]] = (
        *ClusteredBuildbotService.compare_attrs,
        'builderNames',
        'properties',
        'codebases',
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.enabled = True
        self._enable_consumer = None
        self._change_consumer = None
        self._change_consumption_lock = defer.DeferredLock()

    def checkConfig(self, builderNames, properties=None, codebases=None, priority=None):
        ok = True
        if interfaces.IRenderable.providedBy(builderNames):
            pass
        elif isinstance(builderNames, (list, tuple)):
            for b in builderNames:
                if not isinstance(b, str) and not interfaces.IRenderable.providedBy(b):
                    ok = False
        else:
            ok = False
        if not ok:
            config.error(
                "The builderNames argument to a scheduler must be a list "
                "of Builder names or an IRenderable object that will render"
                "to a list of builder names."
            )

        self.builderNames = builderNames

        # Set the codebases that are necessary to process the changes
        # These codebases will always result in a sourcestamp with or without
        # changes
        known_keys = set(['branch', 'repository', 'revision'])

        if codebases is None:
            codebases = self.DEFAULT_CODEBASES.copy()

        if codebases is None:
            config.error("Codebases cannot be None")
        elif isinstance(codebases, list):
            pass
        elif not isinstance(codebases, dict):
            config.error("Codebases must be a dict of dicts, or list of strings")
        else:
            for codebase, attrs in codebases.items():
                if not isinstance(attrs, dict):
                    config.error("Codebases must be a dict of dicts")
                else:
                    unk = set(attrs) - known_keys
                    if unk:
                        config.error(
                            f"Unknown codebase keys {', '.join(unk)} for codebase {codebase}"
                        )

        if priority and not isinstance(priority, int) and not callable(priority):
            config.error(
                f"Invalid type for priority: {type(priority)}. "
                "It must either be an integer or a function"
            )

    @defer.inlineCallbacks
    def reconfigService(self, builderNames, properties=None, codebases=None, priority=None):
        yield super().reconfigService()

        if codebases is None:
            codebases = self.DEFAULT_CODEBASES.copy()

        self.builderNames = builderNames

        if properties is None:
            properties = {}
        self.properties = Properties()
        self.properties.update(properties, "Scheduler")
        self.properties.setProperty("scheduler", self.name, "Scheduler")

        if isinstance(codebases, list):
            codebases = {codebase: {} for codebase in codebases}
        self.codebases = codebases

        self.priority = priority

    def __repr__(self):
        """
        Provide a meaningful string representation of scheduler.
        """
        return (
            f'<{self.__class__.__name__}({self.name}, {self.builderNames}, enabled={self.enabled})>'
        )

    # activity handling
    @defer.inlineCallbacks
    def activate(self):
        if not self.enabled:
            return None

        # even if we aren't called via _activityPoll(), at this point we
        # need to ensure the service id is set correctly
        if self.serviceid is None:
            self.serviceid = yield self._getServiceId()
            assert self.serviceid is not None

        schedulerData = yield self._getScheduler(self.serviceid)

        if schedulerData:
            self.enabled = schedulerData.enabled

        if not self._enable_consumer:
            yield self.startConsumingEnableEvents()
        return None

    def _enabledCallback(self, key, msg):
        if msg['enabled']:
            self.enabled = True
            d = self.activate()
        else:
            d = self.deactivate()

            def fn(x):
                self.enabled = False

            d.addCallback(fn)
        return d

    @defer.inlineCallbacks
    def deactivate(self):
        if not self.enabled:
            return None
        yield self._stopConsumingChanges()
        return None

    # service handling

    def _getServiceId(self):
        return self.master.data.updates.findSchedulerId(self.name)

    def _getScheduler(self, sid):
        return self.master.db.schedulers.getScheduler(sid)

    def _claimService(self):
        return self.master.data.updates.trySetSchedulerMaster(self.serviceid, self.master.masterid)

    def _unclaimService(self):
        return self.master.data.updates.trySetSchedulerMaster(self.serviceid, None)

    # status queries

    # deprecated: these aren't compatible with distributed schedulers

    def listBuilderNames(self):
        return self.builderNames

    # change handling

    @defer.inlineCallbacks
    def startConsumingChanges(self, fileIsImportant=None, change_filter=None, onlyImportant=False):
        assert fileIsImportant is None or callable(fileIsImportant)

        # register for changes with the data API
        assert not self._change_consumer
        self._change_consumer = yield self.master.mq.startConsuming(
            lambda k, m: self._changeCallback(k, m, fileIsImportant, change_filter, onlyImportant),
            ('changes', None, 'new'),
        )

    @defer.inlineCallbacks
    def startConsumingEnableEvents(self):
        assert not self._enable_consumer
        self._enable_consumer = yield self.master.mq.startConsuming(
            self._enabledCallback, ('schedulers', str(self.serviceid), 'updated')
        )

    @defer.inlineCallbacks
    def _changeCallback(self, key, msg, fileIsImportant, change_filter, onlyImportant):
        # ignore changes delivered while we're not running
        if not self._change_consumer:
            return

        # get a change object, since the API requires it
        chdict = yield self.master.db.changes.getChange(msg['changeid'])
        change = yield changes.Change.fromChdict(self.master, chdict)

        # filter it
        if change_filter and not change_filter.filter_change(change):
            return

        if change.codebase not in self.codebases:
            log.msg(
                format='change contains codebase %(codebase)s that is '
                'not processed by scheduler %(name)s',
                codebase=change.codebase,
                name=self.name,
            )
            return

        if fileIsImportant:
            try:
                important = fileIsImportant(change)
                if not important and onlyImportant:
                    return
            except Exception as e:
                log.err(e, f'in fileIsImportant check for {change}')
                return
        else:
            important = True

        # use change_consumption_lock to ensure the service does not stop
        # while this change is being processed
        d = self._change_consumption_lock.run(self.gotChange, change, important)
        d.addErrback(log.err, 'while processing change')

    def _stopConsumingChanges(self):
        # (note: called automatically in deactivate)

        # acquire the lock change consumption lock to ensure that any change
        # consumption is complete before we are done stopping consumption
        def stop():
            if self._change_consumer:
                self._change_consumer.stopConsuming()
                self._change_consumer = None

        return self._change_consumption_lock.run(stop)

    def gotChange(self, change, important):
        raise NotImplementedError

    # starting builds

    @defer.inlineCallbacks
    def addBuildsetForSourceStampsWithDefaults(
        self,
        reason,
        sourcestamps=None,
        waited_for=False,
        properties=None,
        builderNames=None,
        priority=None,
        **kw,
    ):
        if sourcestamps is None:
            sourcestamps = []

        # convert sourcestamps to a dictionary keyed by codebase
        stampsByCodebase = {}
        for ss in sourcestamps:
            cb = ss['codebase']
            if cb in stampsByCodebase:
                raise RuntimeError("multiple sourcestamps with same codebase")
            stampsByCodebase[cb] = ss

        # Merge codebases with the passed list of sourcestamps
        # This results in a new sourcestamp for each codebase
        stampsWithDefaults = []
        for codebase in self.codebases:
            cb = yield self.getCodebaseDict(codebase)
            ss = {
                'codebase': codebase,
                'repository': cb.get('repository', ''),
                'branch': cb.get('branch', None),
                'revision': cb.get('revision', None),
                'project': '',
            }
            # apply info from passed sourcestamps onto the configured default
            # sourcestamp attributes for this codebase.
            ss.update(stampsByCodebase.get(codebase, {}))
            stampsWithDefaults.append(ss)

        # fill in any supplied sourcestamps that aren't for a codebase in the
        # scheduler's codebase dictionary
        for codebase in set(stampsByCodebase) - set(self.codebases):
            cb = stampsByCodebase[codebase]
            ss = {
                'codebase': codebase,
                'repository': cb.get('repository', ''),
                'branch': cb.get('branch', None),
                'revision': cb.get('revision', None),
                'project': '',
            }
            stampsWithDefaults.append(ss)

        rv = yield self.addBuildsetForSourceStamps(
            sourcestamps=stampsWithDefaults,
            reason=reason,
            waited_for=waited_for,
            properties=properties,
            builderNames=builderNames,
            priority=priority,
            **kw,
        )
        return rv

    def getCodebaseDict(self, codebase):
        # Hook for subclasses to change codebase parameters when a codebase does
        # not have a change associated with it.
        try:
            return defer.succeed(self.codebases[codebase])
        except KeyError:
            return defer.fail()

    @defer.inlineCallbacks
    def addBuildsetForChanges(
        self,
        waited_for=False,
        reason='',
        external_idstring=None,
        changeids=None,
        builderNames=None,
        properties=None,
        priority=None,
        **kw,
    ):
        if changeids is None:
            changeids = []
        changesByCodebase = {}

        def get_last_change_for_codebase(codebase):
            return max(changesByCodebase[codebase], key=lambda change: change.changeid)

        # Changes are retrieved from database and grouped by their codebase
        for changeid in changeids:
            chdict = yield self.master.db.changes.getChange(changeid)
            changesByCodebase.setdefault(chdict.codebase, []).append(chdict)

        sourcestamps = []
        for codebase in sorted(self.codebases):
            if codebase not in changesByCodebase:
                # codebase has no changes
                # create a sourcestamp that has no changes
                cb = yield self.getCodebaseDict(codebase)

                ss = {
                    'codebase': codebase,
                    'repository': cb.get('repository', ''),
                    'branch': cb.get('branch', None),
                    'revision': cb.get('revision', None),
                    'project': '',
                }
            else:
                lastChange = get_last_change_for_codebase(codebase)
                ss = lastChange.sourcestampid
            sourcestamps.append(ss)

        if priority is None:
            priority = self.priority

        if callable(priority):
            priority = priority(builderNames or self.builderNames, changesByCodebase)
        elif priority is None:
            priority = 0

        # add one buildset, using the calculated sourcestamps
        bsid, brids = yield self.addBuildsetForSourceStamps(
            waited_for,
            sourcestamps=sourcestamps,
            reason=reason,
            external_idstring=external_idstring,
            builderNames=builderNames,
            properties=properties,
            priority=priority,
            **kw,
        )

        return (bsid, brids)

    @defer.inlineCallbacks
    def addBuildsetForSourceStamps(
        self,
        waited_for=False,
        sourcestamps=None,
        reason='',
        external_idstring=None,
        properties=None,
        builderNames=None,
        priority=None,
        **kw,
    ):
        if sourcestamps is None:
            sourcestamps = []
        # combine properties
        if properties:
            properties.updateFromProperties(self.properties)
        else:
            properties = self.properties

        # make a fresh copy that we actually can modify safely
        properties = Properties.fromDict(properties.asDict())

        # make extra info available from properties.render()
        properties.master = self.master
        properties.sourcestamps = []
        properties.changes = []
        for ss in sourcestamps:
            if isinstance(ss, int):
                # fetch actual sourcestamp and changes from data API
                properties.sourcestamps.append((yield self.master.data.get(('sourcestamps', ss))))
                properties.changes.extend(
                    (yield self.master.data.get(('sourcestamps', ss, 'changes')))
                )
            else:
                # sourcestamp with no change, see addBuildsetForChanges
                properties.sourcestamps.append(ss)

        for c in properties.changes:
            properties.updateFromProperties(Properties.fromDict(c['properties']))

        # apply the default builderNames
        if not builderNames:
            builderNames = self.builderNames

        # dynamically get the builder list to schedule
        builderNames = yield properties.render(builderNames)

        # Get the builder ids
        # Note that there is a data.updates.findBuilderId(name)
        # but that would merely only optimize the single builder case, while
        # probably the multiple builder case will be severely impacted by the
        # several db requests needed.
        builderids = []
        for bldr in (yield self.master.data.get(('builders',))):
            if bldr['name'] in builderNames:
                builderids.append(bldr['builderid'])

        # translate properties object into a dict as required by the
        # addBuildset method
        properties_dict = yield properties.render(properties.asDict())

        if priority is None:
            priority = 0

        bsid, brids = yield self.master.data.updates.addBuildset(
            scheduler=self.name,
            sourcestamps=sourcestamps,
            reason=reason,
            waited_for=waited_for,
            properties=properties_dict,
            builderids=builderids,
            external_idstring=external_idstring,
            priority=priority,
            **kw,
        )
        return (bsid, brids)
