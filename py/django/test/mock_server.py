# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~
import cgi  # pylint: disable=deprecated-module
import datetime
import gc
import json
import logging
import re
import time
import uuid
import warnings
from abc import abstractmethod
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from threading import Event, Lock, Thread
from typing import Union
from urllib.parse import parse_qs

import requests
from django.conf import settings
from django.http import Http404, HttpResponse
from django.test import Client
from django.utils import timezone

# from shopify.models import WebHookCall
from olib.py.django.test.runner import get_test_thread_id, measure_runtime
from olib.py.utils.str import long_int_to_str, str_to_long_int
from olib.py.utils.synchronization import synchronized
from olib.py.utils.url import split_url

logger = logging.getLogger(__name__)


class MockServerException(Exception):
    pass


class MockServerTimeoutException(Exception):
    """Raise to cause timeout"""


class MockServerFakeOrInvalidException(Exception):
    """Raise to return message 'looks fake or invalid'"""


class MockServerOkReturnException(Exception):
    """Returns a valid response, but call implementation"""


class MockServerCustomError(Exception):
    def __init__(self, errorMsg, data, status_code=None, silent=False):
        super().__init__(errorMsg)
        self.errorMsg = errorMsg
        self.data = data
        self.status_code = status_code or requests.codes.bad_request  # pylint: disable=no-member
        self.silent = silent


class MockServerRedirect(Exception):
    """Does not mean something is wrong.. Simply a desire for a subclass to return a redirect"""


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """Handle requests in a separate thread."""


class MockServerClearable:
    def clear(self):
        pass


def mock_server_reset_all():
    """Performs a safe reset of all mock servers, by waiting for all to finish hooks first, then
    resetting them"""

    # Wait for all hooks first
    seenParents = set()
    for server in MockServer.allRunning:

        if hasattr(server, 'waitHookCompletion'):
            logger.info(f"early hook completion for {server.name} on port {server.port}")
            getattr(server, 'waitHookCompletion')()

        if server.parent is not None and server.parent not in seenParents:
            if hasattr(server.parent, 'waitHookCompletion'):
                logger.info('early hook completion for parent')
                getattr(server.parent, 'waitHookCompletion')()

            seenParents.add(server.parent)

    # Now reset all. Items will be removed from list while traversing, so copy list.
    seenParents = set()
    for server in list(MockServer.allRunning):
        if server.parent is not None:
            if server.parent not in seenParents:
                server.parent.reset()
                seenParents.add(server.parent)

        else:
            server.reset()


# import socketserver
# class MockTCPServer(socketserver.TCPServer):
#    allow_reause_address = True


class MockServerInjectError:
    def __init__(
        self,
        target,
        funcOrExceptionOrMessage=None,
        count=1,
        stall=False,
        condition=None,
    ):
        """
        If func is an exception object or returns an exception object, this object will be raised
        :param stall: Set to stall until stall is cleared
        """
        self.target = target
        self.reg = re.compile(target)
        self.func_or_exception: Callable | Exception | None

        if isinstance(funcOrExceptionOrMessage, str):
            self.func_or_exception = MockServerException(funcOrExceptionOrMessage)
        elif funcOrExceptionOrMessage is not None:
            self.func_or_exception = funcOrExceptionOrMessage
        else:
            self.func_or_exception = MockServerException('Injected error') if not stall else None

        self.count = count
        self.stall = stall
        self.condition = condition

    def injectOnMatch(self, action, get, post):
        if self.count > 0 and self.reg.match(action) and (self.condition is None or self.condition(action, get, post)):
            self.count -= 1
            while self.stall:
                # Stall request until stall is cleared
                time.sleep(0.1)

            if self.func_or_exception is not None:
                ret = self.func_or_exception() if callable(self.func_or_exception) else self.func_or_exception
                if isinstance(ret, Exception):
                    raise ret


class MockServerUtils(MockServerClearable):
    """Utility functions for helping servers managing data"""

    @synchronized
    def getCreateId(self, objects, newObject=None, idName='id', baseId=1, numeric=True):
        if newObject is None or idName not in newObject:
            # Create new id
            if not objects:
                return baseId

            if numeric:
                return max(o[idName] for k, o in objects.items()) + 1

            return long_int_to_str(max(str_to_long_int(o[idName]) for k, o in objects.items()) + 1)

        id = newObject[idName]
        if numeric:
            id = int(id)

        if id in objects:
            raise MockServerException(f"Object with id {id} already present. New: {newObject}, Existing: {objects[id]}")

        if numeric and id <= 0:
            raise MockServerException(f"Object id must be non-zero positive. Found {id} for {newObject}")

        return id

    # Hash-based id. A string, not a number
    @synchronized
    def getCreateHashId(self, objects, newObject, idName='id'):
        if not idName in newObject:
            # Create new id
            id = str(uuid.uuid4())
        else:
            id = newObject[idName]
            if id in objects:
                raise MockServerException(
                    f"Object with id {id} already present. New: {newObject}, Existing: {objects[id]}"
                )
        return id

    @synchronized
    def getValidateId(self, objects, newObject, id, idName='id'):
        if idName in newObject and newObject[idName] != id:
            raise MockServerException('Different ids on same object')

        if id not in objects:
            # This error is configured for shopify.. make more generic if necessary
            raise MockServerCustomError(f"Object with id {id} not present for update", {'errors': 'Not Found'})

        return id

    # @staticmethod
    # def failOnDuplicate(typeName, objects, attr):
    #     """If two items in objects list has the same attribe, fails"""
    #     ctr = Counter(o[attr] for _, o in objects.items())
    #     val, count = ctr.most_common(1)[0]
    #     if count > 1:
    #         #This error is configured for shopify.. make more generic if necessary
    #         raise MockServerCustomError(f'Two duplicate {typeName}s for {attr}={val}', {'errors': {attr: 'has already been taken'}})

    @synchronized
    def getCreateSubObjectId(self, name, superObjsMap, create=True, subObj=None):
        # logger.debug("SUPEROBJS: {}".format(superObjsMap))
        if subObj is not None and 'id' in subObj:
            # Verify unique if creating new object. Not necessary if updating
            if create and any(
                any(
                    v['id'] == subObj['id'] and v is not subObj
                    for v in (p[name] if isinstance(p[name], list) else [p[name]])
                )
                for k, p in superObjsMap.items()
                if name in p
            ):
                raise MockServerException(f"{name} id {subObj['id']} already exists")
            if subObj['id'] <= 0:
                raise MockServerException(f"{name} id {subObj['id']} is not non-zero positive")

            return subObj['id']

        # Create new subObj id
        return (
            max(
                (
                    (
                        max((v['id'] for v in p[name] if 'id' in v), default=0)
                        if isinstance(p[name], list)
                        else p[name].get('id', 0)
                    )
                    for k, p in superObjsMap.items()
                    if name in p
                ),
                default=0,
            )
            + 1
        )

    @synchronized
    def updateObject(self, cur, new, idName='key'):
        # Call unsynchronized handler to avoid stepping through synchronization on every recursion
        return self._updateObject(cur, new, idName)

    def _updateObject(self, cur, new, idName):
        for k, v in new.items():  # Loop new items
            if isinstance(v, dict):
                newVal = self._updateObject(cur.get(k, {}), v, idName)
            elif isinstance(v, list):
                newVal = cur[k][:] if k in cur else []
                if any('id' in vi or idName in vi for vi in v if isinstance(vi, dict)):
                    # List contains objects
                    for vi in v:
                        present = False
                        # Some list items are objects, and have ids. If id is aready present, update it
                        if len(newVal) > 0 and isinstance(vi, dict) and 'id' in vi or idName in vi:
                            idName = 'id' if 'id' in vi else (idName if idName in vi else 'id')  # Metadata uses 'key'
                            index = next(
                                (i for i, ci in enumerate(newVal) if idName in ci and ci[idName] == vi[idName]),
                                None,
                            )  # Find index of existing
                            # logger.info("cur: {}".format(cur))
                            # logger.info("newVal: {}".format(newVal))
                            # logger.info("INDEX: {}".format(index))
                            if index is not None:  # Found match in existing list
                                newVal[index] = self._updateObject(newVal[index], vi, idName)
                                present = True

                        if not present:
                            newVal.append(vi)
                else:
                    # Just a list. Overwrite the old one
                    newVal = v

            else:  # Regular value
                newVal = v

            if k not in cur or cur[k] != newVal:
                logger.info(f"Updating cur[{k}] from {cur[k] if k in cur else None} to {newVal}")
            cur[k] = newVal
        return cur


# Base for other mock servers
class MockServerDriver(MockServerClearable):
    allRunning: list['MockServerDriver'] = []

    """Server manager for mock servers"""

    def __init__(self, name):
        super().__init__()

        self.name = name
        self.url: str | None = None
        self.host = None
        self.port = None
        self.terminating = False
        self.running = False
        self.softStopped = False
        self.parent = None

        self.mock_server = None
        self.mock_server_thread = None
        self.injectErrors = {}  # Set map {name: MockServerInjectError}
        self.callLog = []

    @staticmethod
    def serverThread(mockServer, testThreadId):
        mockServer.serve_forever(poll_interval=0.01)

    # Starts and returns server
    @measure_runtime('mock-startstop')
    def start(self, testName='unnamed'):
        assert self.url is not None  # nosec: assert_used

        if self.softStopped:
            self.softStopped = False
            logger.info(f"soft-start on port {self.port} for {testName}")
            return

        match = re.match(r'https?:*\/\/([^\/:]+):(\d+).*', self.url)
        if match is None:
            raise Exception(f"invalid url for MockServerDriver: {self.url}")
        self.host = match.group(1)
        self.port = int(match.group(2))

        handler = self.createHandler()
        self.terminating = False

        # Retry binding to port a couple of times if it does not work immediately
        retry = 5
        self.mock_server = None
        logger.info(f"connecting on port {self.port} for {testName}")

        print(f"@{get_test_thread_id()} connecting to {self.port} for {testName}")

        while retry > 0:
            try:
                # print(f'opening PORT {self.port} for {self.name}')
                self.mock_server = ThreadedHTTPServer((self.host, self.port), handler)
                # self.mock_server = MockTCPServer((self.host, self.port), handler)
                break
            except:  # pylint: disable=bare-except
                logger.exception(f"unable to connect on port {self.port} for {testName}")
                time.sleep(1)
                logger.info('retrying connection')
                retry -= 1

        if self.mock_server is None:
            raise MockServerException(f"Unable to bind on port {self.port} for {testName}. Already in use")

        self.mock_server_thread = Thread(
            target=MockServerDriver.serverThread,
            args=(self.mock_server, get_test_thread_id()),
            name=self.name + str(get_test_thread_id()),
        )
        self.mock_server_thread.daemon = True
        self.mock_server_thread.start()
        self.running = True

        type(self).allRunning.append(self)

    def softStop(self):
        logger.info(f"soft-stop on port {self.port}")
        self.softStopped = True

    def isSoftStopped(self):
        return self.softStopped

    # @ignoreResourceWarnings
    @measure_runtime('mock-startstop')
    def stop(self, *args, **kwargs):
        assert self.mock_server is not None  # nosec: assert_used
        assert self.mock_server_thread is not None  # nosec: assert_used

        # Wait for hooks if necessary. Hooks are managed in another mixin, so if available, do it
        if hasattr(self, 'waitHookCompletion'):
            logger.info(f"about to shut down {self.name} on port {self.port}")
            getattr(self, 'waitHookCompletion')()

        logger.info(f"shutting down {self.name} on port {self.port}")
        self.terminating = True
        with warnings.catch_warnings():
            logger.info(f"close begin for {self.name} on port {self.port}")
            warnings.simplefilter('ignore', ResourceWarning)
            self.mock_server.shutdown()
            # logger.info(f'close mid for {self.name} on port {self.port}')
            self.mock_server.server_close()
            logger.info(f"close end for {self.name} on port {self.port}")

        logger.info(f"waiting for {self.name} server thread to end on port {self.port}")
        self.mock_server_thread.join()
        logger.info(f"done waiting for {self.name} on port {self.port}")
        self.running = False
        self.terminating = False

        type(self).allRunning.remove(self)

    def createHandler(self):
        """Return handler map for server"""
        raise NotImplementedError

    @synchronized
    def clear(self):
        """Override to clear data values"""
        self.callLog = []

        super().clear()

    def isRunning(self):
        return self.running

    @synchronized
    def reset(self):
        self.injectErrors = {}
        self.softStop()
        self.clear()
        gc.collect()


class MockRequestHandler(BaseHTTPRequestHandler):

    def __init__(
        self,
        mockServer,
        handlers,
        *args,
        returnType='application/json',
        mockHandler=None,
        **kwargs,
    ):
        self.mockServer = mockServer
        self.handlers = handlers
        self.returnType = returnType
        self.mockHandler = mockHandler or mockServer

        super().__init__(*args, **kwargs)

    def doMap(self, method, path, get, post):
        action = method + ' ' + path
        self.mockServer.callLog.append(action)
        # Execute
        for m in self.handlers:
            match = re.match(m[0], action)
            if match:
                options = m[1] if isinstance(m[1], str) else ''

                # Execute any error injections
                if self.mockServer.injectErrors:
                    for _, ie in self.mockServer.injectErrors.items():
                        if ie is not None:
                            ie.injectOnMatch(action, get, post)

                args = match.groups()
                logger.debug(f" match on {m[0]} with args {args}")

                if 'H' in options:
                    # Pass header into handler function
                    args = (self.headers, *args)

                if 'X' in options:
                    self.returnType = 'text/xml'

                # Execute
                ret = m[-1](self.mockHandler, get, post, *args)

                if isinstance(ret, Exception):
                    raise ret
                if 'C' in options:
                    # Continue processing other handlers
                    continue

                self.returnData(ret)
                return

        raise Exception(f"Unkown API url {method} {path} for server {self.mockServer.name}")

    def doAny(self, method):
        if self.mockServer.softStopped:
            self.returnBadRequest(
                f"Server is soft-down: {self.mockServer.name}",
                status_code=503,
                silent=False,
            )  # 503 - service unavailable
            return
            # raise Exception('Server is soft-down')

            # We want to requester to raise an exception. Return without providing any response
            # return

        logger.debug(f"Mock HTTP Request START on port {self.mockServer.port}")

        # GET params
        path, getvars = split_url(self.path)

        # POST params
        postvars: dict[str, str] | str | None = {}
        if method not in ('GET',):
            if self.headers['content-type'] is None:
                postvars = None
            else:
                ctype, pdict = cgi.parse_header(self.headers['content-type'])
                if ctype == 'multipart/form-data':
                    multi = cgi.parse_multipart(self.rfile, pdict)  # type: ignore
                    postvars = {k.decode('utf-8'): v[0].decode('utf-8') for k, v in multi.items()}  # type: ignore
                elif ctype == 'application/x-www-form-urlencoded':
                    length = int(self.headers['content-length'])
                    parsed = parse_qs(self.rfile.read(length), keep_blank_values=True)
                    postvars = {k.decode('utf-8'): v[0].decode('utf-8') for k, v in parsed.items()}
                elif ctype == 'application/json':
                    postvars = json.loads(self.rfile.read(int(self.headers['content-length'])).decode('utf-8'))
                elif ctype == 'application/graphql':
                    # Simply decode to string
                    postvars = self.rfile.read(int(self.headers['content-length'])).decode('utf-8')
                elif ctype == 'text/xml':
                    # NOTE: Use callback to handle XML?
                    postvars = self.rfile.read(int(self.headers['content-length'])).decode('utf-8')
                else:
                    raise MockServerException(f"Unknown content-type: {ctype}")

        info = f"{method} {path}: GET {getvars}, POST {postvars} on port {self.mockServer.port}"

        if not self.mockServer.running or self.mockServer.terminating or self.mockServer.softStopped:
            raise Exception(
                'Tried to execute API call against server that is on its way down (or down). This is likely because processes are active past the end of a test, and should be fixed in the test\n'
                + info
            )

        logger.debug(info)

        # Catch arbitrary issues
        try:
            self.doMap(method, path, getvars, postvars)
        except MockServerOkReturnException:
            self.returnData('')
        except MockServerRedirect as e:
            self.returnRedirect(str(e))
        except MockServerTimeoutException:
            self.returnTimeout()  # Cause timeout
        except MockServerFakeOrInvalidException as e:
            self.returnBadRequest('invalid email', jsonData={'detail': str(e) or 'looks fake or invalid'})
        except MockServerCustomError as e:
            self.returnBadRequest(e.errorMsg, jsonData=e.data, status_code=e.status_code, silent=e.silent)
        except Http404:
            self.returnNotFound()
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception(f"{type(e).__name__}: {e}")
            self.returnBadRequest(str(e))

        logger.debug(f"Mock HTTP Request END on port {self.mockServer.port}")

    def do_GET(self):
        self.doAny('GET')

    def do_POST(self):
        self.doAny('POST')

    def do_PUT(self):
        self.doAny('PUT')

    def do_DELETE(self):
        self.doAny('DELETE')

    def do_PATCH(self):
        self.doAny('PATCH')

    def do_OPTIONS(self):
        self.send_response(200, 'ok')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS, PUT, DELETE, PATCH')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
        self.wfile.write(b'')

    def returnRedirect(self, url):
        """If url does not start with http(s), assume redirect back to referrer's host"""
        if not url.startswith('http'):
            referer = self.headers['Referer']
            refHost = re.match(r'https?:\/\/[^\/]+', referer).group(0)  # type: ignore
            url = refHost + url

        logger.info(f"Returning redirect to: {url}")
        self.send_response(302)  # Temporary redirect
        self.send_header('Location', url)
        self.end_headers()
        self.wfile.write(b'')

    def returnTimeout(self):
        logger.info('Returing timeout')
        self.send_response(requests.codes.gateway_timeout)  # pylint: disable=no-member
        self.end_headers()
        self.wfile.write(b'')

    def returnBadRequest(
        self, error, jsonData=None, status_code=requests.codes.bad_request, silent=False
    ):  # pylint: disable=no-member
        if not silent:
            logger.error(f"Bad request: {error}")
        jsonData = jsonData or {}
        self.send_response(status_code)
        self.end_headers()

        response_content = json.dumps(jsonData)
        logger.info(f"returning json: {response_content[:2000]}")
        self.wfile.write(response_content.encode('utf-8'))

    def returnNotFound(self):
        self.send_response(404)
        self.end_headers()
        self.wfile.write(b'')

    def returnData(self, data):
        returnType = self.returnType
        statusCode = 200
        headers = {}

        if isinstance(data, HttpResponse):
            statusCode = data.status_code
            headers = dict(data.items())
            returnType = data['content-type']
            data = data.content

        else:
            # Add response headers.
            headers['X-Rate-Limit-Limit'] = '60'
            headers['X-Rate-Limit-Remaining'] = '60'
            headers['X-Rate-Limit-Reset'] = '0'
            headers['X-Shopify-Shop-Api-Call-Limit'] = '0/100'

            # Bold specific
            headers['x-ratelimit-limit'] = '20 requests per second'
            headers['x-ratelimit-remaining'] = '15 requests per second'

            headers['Access-Control-Allow-Origin'] = '*'  # Allow javascript to call api from browser
            headers['Content-Type'] = f"{returnType}; charset=utf-8"

            if returnType == 'application/json':
                data = json.dumps(data)

            data = data.encode('utf-8')

        self.send_response(statusCode)
        for k, v in headers.items():
            self.send_header(k, v)
        self.end_headers()

        logger.info(f"returning {returnType}: {data}")
        self.wfile.write(data)

    def log_message(self, format, *args):
        return  # Supress log messages

    def log_request(self, code='-', size='-'):
        return  # Supress log messages


class WebHookMixin(MockServerClearable):
    hookLock = Lock()

    def __init__(self, *args, **kwargs):
        super().__init__()

        self.threads = []
        self.client = Client()
        self.stallHooks: set[str] | None = None  # Set of webhooks to stall on
        self.hooksDisabled = set()  # Names of disabled hooks

    @synchronized
    def clear(self):
        """Override to clear data values"""
        self.stallHooks = None
        self.hooksDisabled = set()

        super().clear()

    @abstractmethod
    def _callHook(self, client, *args, **kwargs):
        """Must be implemented by consumer of mixin to actually call the webhook
        :return: (status, retry) meaning actual status, and whether to fail on error or retry
        """

    @measure_runtime('mock-hook')
    def callHookWrapper(self, expResponse, ep, started, args):
        # Signal to the world that we have started. Important, because there is a gap in time before thread.is_alive is set when a thread starts. With the
        #'started' event, we can now close that gap
        started.set()

        # Wait for any stall to finish
        logger.info(f"stallhooks? ep: {ep}, stall on: {self.stallHooks}")
        if self.stallHooks is not None and ep in self.stallHooks:
            logger.info(f"stalling hook {ep}")
            while self.stallHooks:
                time.sleep(0.1)
            logger.info(f"stalling hook {ep} done")

        # Ensure previous call has completed by briefly claiming the mutex. Don't want to hold it though,
        # as further calls to mock can happen within the hook call
        self._hookBarrier()

        # Only allow one hook to run at a time, as hooks trigger celery tasks which are eager in testing, and we end up
        # with lots of nastyness if they run on top of eachother
        with WebHookMixin.hookLock:
            logger.info(f"hooklock acquired ({id(WebHookMixin.hookLock)}) for {ep}")

            try:
                retries = 10
                while retries > 0:
                    logger.debug(f"callHook BEGIN with data {[ep, *args]}")
                    (url, status, retry) = self._callHook(self.client, ep, *args)
                    logger.debug(f"callHook {url} COMPLETE with response {status}")

                    if status == expResponse:
                        # Done
                        return

                    if retry:
                        logger.debug(f"callHook {url} will retry")
                        time.sleep(0.1)
                        retries -= 1
                        continue

                    raise MockServerException(f"Hook returned status code {status} for data\n{args}")

                # Used all retries. Still unsucessful
                raise MockServerException(f"Hook failed too many times for data\n{args}")
            except:  # pylint: disable=bare-except
                logger.exception('hook call failed')

    @synchronized
    def _hookBarrier(self):
        """Called by hook to wait until execution has left mock_shopify before launching hooks through synchronization"""
        return True

    @synchronized
    def callHook(self, ep, *args, expResponse=200):
        if self.client is None:
            logger.info(f"Hook {ep} not called due to self.client is None")

        elif ep in self.hooksDisabled:
            logger.info(f"Hook {ep} not called due to being disabled. Disabled hooks: {self.hooksDisabled}")

        else:
            # Call hook in new thread
            started = Event()
            t = Thread(target=self.callHookWrapper, args=(expResponse, ep, started, args))
            t.start()
            self.threads.append((ep, t, started))

    # Not synchronized, as the semaphore must be released to allow any
    # pending api calls to finish. Else there will be deadlock
    def waitHookCompletion(self, threadsToCheck=None, ignoreStalled=True):
        """
        :param ignoreStalled: return from wait if only stalled hooks are left
        """
        WAIT_TIMEOUT = datetime.timedelta(seconds=30)

        if hasattr(self, 'isRunning') and not self.isRunning():
            logger.debug('no hooks running')
            return

        # Don't repeat wait messages. Also tracks time waited for a given event
        pollStart: dict[str, datetime.datetime] = {}

        while True:
            # Wait for all threads to finish
            threads = threadsToCheck or self.getThreads()

            # Only print waiting-status if not in debugger, because it can be very difficult to debug when these messages keep spewing out
            # for ep, t in threads:
            #    logger.info(f'done-waiting check: {t.is_alive()}, {ignoreStalled}, {self.stallHooks}, {ep}')

            if not threads or all(
                (started.is_set() and not t.is_alive())
                or (ignoreStalled and self.stallHooks is not None and ep in self.stallHooks)
                for ep, t, started in threads
            ):
                threadStatus = [
                    ('not-started' if not started else 'running' if t.is_alive() else 'completed')
                    for _, t, started in threads
                ]
                logger.info(f"exit wait, thrads: {threadStatus}")
                for m in pollStart:
                    logger.debug(f"done waiting: {m}")
                return  # Done

            # Wait for threads to finish
            now = timezone.now()
            for ep, t, _ in threads:
                tStart = pollStart.get(ep)
                if tStart is None:
                    logger.debug(f"waiting for hook completion: {ep}")
                    pollStart[ep] = now
                elif now - tStart > WAIT_TIMEOUT and not settings.TEST_SELENIUM_TIMEOUT_DISABLE:
                    raise Exception('Timeout while waiting for webhook: {ep}')

                t.join(0.1)

            # Wait for all hooks to be processed (this will mix servers, i.e. shopify will wait for bold items etc)
            # if WebHookCall.objects.filter(state__in=(WebHookCall.State.RECEIVED.value, WebHookCall.State.POSTPONED.value)).exists():
            #    time.sleep(0.1)

    @synchronized
    def getThreads(self):
        # Remove any threads not alive
        self.threads = [(ep, t, started) for ep, t, started in self.threads if not started.is_set() or t.is_alive()]
        return self.threads.copy()


def createMockRequestHandler(mockServer, handlers, returnType='application/json', mockHandler=None):
    """Create a request handler class with embedded link to mock server and handlers
    :param mockHandler: Set to object ot pass as first argument to handlers. If not set, mockServer is passed
    """

    class SpecificMockRequestHandler(MockRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(
                mockServer,
                handlers,
                *args,
                returnType=returnType,
                mockHandler=mockHandler,
                **kwargs,
            )

    return SpecificMockRequestHandler


class MockServer(
    MockServerDriver, MockServerUtils
):  # pylint: disable=abstract-method # pylint does not understand abstract subclass
    pass


class MockMultiServer(MockServerUtils):
    instance: Union['MockMultiServer', None] = (
        None  # Each sub-class gets a copy of this as long as it is accessed through cls
    )

    """Allows servies that expose servers through multiple URLs / IP addresses (bold is an example)"""

    def __init__(self, spec=None):
        super().__init__()

        self.spec = spec
        self.servers = {}

    def getUrl(self, serverName):
        return self.servers[serverName].url

    @classmethod
    def getSingletonServer(cls, testName, initDataset=False):
        """Create a multiserver instance and start all servers that are part of it"""
        if cls.instance is None:
            cls.instance = cls()

        cls.instance.setup(initDataset)
        cls.instance.start(testName)

        return cls.instance

    @classmethod
    def getInstIfLive(cls, shopifyType='main'):
        if cls.instance is not None and all(
            server.running and not server.terminating and not server.softStopped
            for _, server in cls.instance.servers.items()
        ):
            return cls.instance

        return None

    def start(self, testName):
        """Start all servers"""
        for serverName, serverSpec in self.spec.items():
            server = self.servers.get(serverName)

            if (url_settings := serverSpec.get('urlSettings')) is not None:
                if 'originalUrl' not in serverSpec:
                    serverSpec['originalUrl'] = getattr(settings, url_settings[0])
                    serverSpec['originalPort'] = int(getattr(settings, url_settings[1]))

                port = serverSpec['originalPort'] + get_test_thread_id()
                url = serverSpec['originalUrl'].replace(str(serverSpec['originalPort']), str(port))

                setattr(settings, serverSpec['urlSettings'][0], url)

            elif (local_port := serverSpec.get('localPort')) is not None:
                url = f"http://127.0.0.1:{local_port}"
            else:
                raise Exception('implement other settings scheme or use the one above')

            if server is not None and server.softStopped:
                logger.info(f"soft-start of server {serverName}")
                server.softStopped = False
                continue

            server = MockServerDriver(serverName)
            server.createHandler = lambda server=server, serverSpec=serverSpec: createMockRequestHandler(server, serverSpec['handlers'], mockHandler=self)  # type: ignore
            server.url = url
            server.parent = self
            server.start(testName=f"{testName} - {serverName}")

            self.servers[serverName] = server

    def softStop(self):
        for serverName, server in self.servers.items():
            logger.info(f"soft-stop of server {serverName}")
            server.softStop()

    def isSoftStopped(self):
        return all(server.softStopped for _, server in self.servers.items())

    def stop(self):
        # Wait for hooks if necessary. Hooks are managed in another mixin, so if available, do it
        if hasattr(self, 'waitHookCompletion'):
            logger.info(f"about to shut down {type(self)}")
            getattr(self, 'waitHookCompletion')()

        for _, server in self.servers.items():
            server.stop()

    def isRunning(self):
        return any(s.isRunning() for _, s in self.servers.items())

    def getCallLogs(self):
        """Returns call logs for each sub server with the server name as prefix"""
        return [f"{server.name} {log}" for _, server in self.servers.items() for log in server.callLog]

    def setup(self, initDataset):
        """Override to allow setup of server
        :param initDataset: Set to pull initial data for the server from the database
        """

    @synchronized
    def reset(self):
        self.softStop()
        self.clear()

    @classmethod
    def getInst(cls):
        inst = cls.instance

        if inst is None:
            raise Exception(f"{cls.__name__} instance requested, but not available")

        return inst

    def clear(self):
        """Override to clear state"""
        for _, server in self.servers.items():
            server.clear()

        super().clear()
