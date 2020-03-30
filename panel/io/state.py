"""
Various utilities for recording and embedding state in a rendered app.
"""
from __future__ import absolute_import, division, unicode_literals

import threading

from weakref import WeakKeyDictionary, WeakSet

import param

from bokeh.document import Document
from bokeh.io import curdoc as _curdoc
from pyviz_comms import CommManager as _CommManager


class _state(param.Parameterized):
    """
    Holds global state associated with running apps, allowing running
    apps to indicate their state to a user.
    """

    busy = param.Boolean(default=False, readonly=True, doc="""
       Whether the application is currently busy processing a user
       callback.""")

    cache = param.Dict(default={}, doc="""
       Global location you can use to cache large datasets or expensive computation results
       across multiple client sessions for a given server.""") 

    webdriver = param.Parameter(default=None, doc="""
      Selenium webdriver used to export bokeh models to pngs.""")

    _curdoc = param.ClassSelector(class_=Document, doc="""
        The bokeh Document for which a server event is currently being
        processed.""")

    # Whether to hold comm events
    _hold = False

    # Used to ensure that events are not scheduled from the wrong thread
    _thread_id = None

    _comm_manager = _CommManager

    # Locations
    _location = None # Global location, e.g. for notebook context
    _locations = WeakKeyDictionary() # Server locations indexed by document

    # An index of all currently active views
    _views = {}

    # For templates to keep reference to their main root
    _fake_roots = []

    # An index of all currently active servers
    _servers = {}

    # Jupyter display handles
    _handles = {}

    # Dictionary of callbacks to be triggered on app load
    _onload = WeakKeyDictionary()

    # Stores a set of locked Websockets, reset after every change event
    _locks = WeakSet()

    # Indicators listening to the busy state
    _indicators = []

    # Endpoints
    _rest_endpoints = {}

    def __repr__(self):
        server_info = []
        for server, panel, docs in self._servers.values():
            server_info.append(
                "{}:{:d} - {!r}".format(server.address or "localhost", server.port, panel)
            )
        if not server_info:
            return "state(servers=[])"
        return "state(servers=[\n  {}\n])".format(",\n  ".join(server_info))

    def kill_all_servers(self):
        """Stop all servers and clear them from the current state."""
        for server_id in self._servers:
            try:
                self._servers[server_id][0].stop()
            except AssertionError:  # can't stop a server twice
                pass
        self._servers = {}

    def _unblocked(self, doc):
        thread = threading.current_thread()
        thread_id = thread.ident if thread else None
        return doc is self.curdoc and self._thread_id == thread_id

    def onload(self, callback):
        """
        Callback that is triggered when a session has been served.
        """
        if self.curdoc is None:
            callback()
            return
        if self.curdoc not in self._onload:
            self._onload[self.curdoc] = []
        self._onload[self.curdoc].append(callback)

    def sync_busy(self, indicator):
        """
        Syncs the busy state with an indicator with a boolean value
        parameter.
        """
        self._indicators.append(indicator)

    @param.depends('busy')
    def _update_busy(self):
        for indicator in self._indicators:
            indicator.value = self.busy

    def publish(self, endpoint, parameterized, input=None, output=None):
        if output is None:
            output = list(parameterized.param)
        self._rest_endpoints[(self.curdoc, endpoint)] = (parameterized, input, output)

    @property
    def curdoc(self):
        if self._curdoc:
            return self._curdoc
        elif _curdoc().session_context:
            return _curdoc()

    @curdoc.setter
    def curdoc(self, doc):
        self._curdoc = doc

    @property
    def cookies(self):
        return self.curdoc.session_context.request.cookies if self.curdoc else {}

    @property
    def headers(self):
        return self.curdoc.session_context.request.headers if self.curdoc else {}

    @property
    def session_args(self):
        return self.curdoc.session_context.request.arguments if self.curdoc else {}

    @property
    def location(self):
        if self.curdoc and self.curdoc not in self._locations:
            from .location import Location
            self._locations[self.curdoc] = loc = Location()
            return loc
        elif self.curdoc is None:
            return self._location
        else:
            return self._locations.get(self.curdoc) if self.curdoc else None


state = _state()
