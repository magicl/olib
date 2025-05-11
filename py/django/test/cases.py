# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~

import gc
import logging
import re
import sys
import time
from contextlib import contextmanager

from django.conf import settings
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import LiveServerTestCase, TestCase, TransactionTestCase
from django.test.utils import override_settings
from pympler import tracker

from olib.py.django.test.debug import breakOnError, breakOnErrorCheckpoint
from olib.py.utils.mem import procMaxMemUsage

logger = logging.getLogger('tests.cases')

prevTest: TestCase | None = None


def testFixtures(*names):
    """Apply fixtures to testcase. No effect on TestCase instances"""

    def decorator(func):
        func._ovr_fixtures = list(names)  # pylint: disable=protected-access
        return func

    return decorator


class TestTimingMixin:
    def __init__(self, *args, **kwargs):
        self.tTestStart = 0.0
        self.tRealStart = 0.0
        # self.tEnd = 0.0
        self.mRssMaxPre = 0
        self.prevTest = None

        # Set by test runner
        self.tTest = 0.0
        self.tReal = 0.0
        self.mRssMaxPost = 0

        super().__init__(*args, **kwargs)

    def setUp(self):
        """Not called for parallel testcases"""
        self.tRealStart = time.time()
        self.mRssMaxPre = procMaxMemUsage()

        global prevTest  # pylint: disable=global-statement
        self.prevTest = prevTest
        prevTest = self

        super().setUp()  # type: ignore[misc]

        self.tTestStart = time.time()

    def tearDown(self):
        """Called after 'addSuccess', so can't capture end-time here"""
        super().tearDown()  # type: ignore[misc]
        self.tEnd = time.time()


class MemDebugMixin:
    memTracker: tracker.SummaryTracker | None = None

    def setUp(self):
        """Not called for parallel testcases"""
        cls = type(self)
        if settings.TEST_DEBUG_MEM and cls.memTracker is None:
            cls.memTracker = tracker.SummaryTracker()

        super().setUp()  # type: ignore[misc]

    def tearDown(self):
        """Called after 'addSuccess', so can't capture end-time here"""
        super().tearDown()  # type: ignore[misc]

        # Also do log monitoring here
        cls = type(self)
        if cls.memTracker is not None:
            gc.collect()
            cls.memTracker.print_diff()


class ConfigMixin:
    def __init__(self, *args, **kwargs):
        # No restriction on length of diffs
        self.maxDiff = None
        super().__init__(*args, **kwargs)


class LogMonitorMixin:
    """Checks for any ERROR or WARNING log entries, and will fail the current test if found"""

    class Handler(logging.Handler):
        _exceptions = [
            (
                'kombu.connection',
                'No hostname was supplied. Reverting to default',
            )  # Seems to be an error in Kombu. Should not ahve any effect. See https://github.com/celery/kombu/issues/1357
        ]

        def __init__(self, testcase, *args, **kwargs):
            super().__init__(*args, **kwargs)
            # self.testcase = testcase  # Removed.. don't think this has any use
            self.messages = []

        def clear(self):
            self.messages = []

        def emit(self, record):
            # Only errors and warnings that are not filtered by utils.logging should hit here
            # Make sure they are reported as errors
            if not getattr(record, 'dontFailTest', False):
                # Check if message is in exceptions list
                for exName, exMsg in self._exceptions:
                    if record.name == exName and re.search(exMsg, record.message):
                        logger.info(f"Ignored {record.levelname} from {record.name}: {record.message}")
                        return

                # Allow intercept
                breakOnErrorCheckpoint()

                # Not in exceptions list. Record it
                self.messages.append((record.levelname, record.getMessage()))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Cannot set up handler object in __init__ as it makes this object unpicklable, preventing
        # parallelized tests
        self.handler = None
        self.rootLogger = None

    def _logMonitorMixinInit(self):
        self.handler = self.Handler(self)
        self.handler.setLevel(logging.WARNING)
        self.rootLogger = logging.getLogger('')

    def setUp(self):
        """Mount log monitor"""
        if self.handler is None:
            self._logMonitorMixinInit()

        assert self.handler is not None  # nosec: assert_used
        assert self.rootLogger is not None  # nosec: assert_used

        self.handler.clear()
        self.rootLogger.addHandler(self.handler)

        if settings.TEST_PARALLEL:
            logger.info(f"::{self.id()} PARALLEL TEST START")  # type: ignore[attr-defined]

        super().setUp()  # type: ignore[misc]

    def tearDown(self):
        """Check and remove log monitor"""
        if self.rootLogger is not None:
            self.rootLogger.removeHandler(self.handler)

        if self.handler is not None and self.handler.messages:
            # To prevent a log warning / error from failing a test, add extra={'dontFailTest': True} to the log call
            self.fail(self.handler.messages)  # type: ignore[attr-defined]
        super().tearDown()  # type: ignore[misc]


class AssertHelper:

    def assertEqual(self, *args, **kwargs):
        with breakOnError():
            super().assertEqual(*args, **kwargs)  # type: ignore # pylint: disable=no-member

    def assertNotEqual(self, *args, **kwargs):
        with breakOnError():
            super().assertNotEqual(*args, **kwargs)  # type: ignore # pylint: disable=no-member

    def assertTrue(self, *args, **kwargs):
        with breakOnError():
            super().assertTrue(*args, **kwargs)  # type: ignore # pylint: disable=no-member

    def assertFalse(self, *args, **kwargs):
        with breakOnError():
            super().assertFalse(*args, **kwargs)  # type: ignore # pylint: disable=no-member

    def assertIs(self, *args, **kwargs):
        with breakOnError():
            super().assertIs(*args, **kwargs)  # type: ignore # pylint: disable=no-member

    def assertIsNot(self, *args, **kwargs):
        with breakOnError():
            super().assertIsNot(*args, **kwargs)  # type: ignore # pylint: disable=no-member

    def assertIsNone(self, obj: object, msg: str | None = None) -> None:
        with breakOnError():
            super().assertIsNone(obj, msg)  # type: ignore # pylint: disable=no-member
        assert obj is None  # Help mypy understand the constraint # nosec: assert_used

    def assertIsNotNone(self, obj: object, msg: str | None = None) -> None:
        with breakOnError():
            super().assertIsNotNone(obj, msg)  # type: ignore # pylint: disable=no-member
        assert obj is not None  # Help mypy understand the constraint # nosec: assert_used

    def assertAlmostEqual(self, *args, **kwargs):
        with breakOnError():
            super().assertAlmostEqual(*args, **kwargs)  # type: ignore # pylint: disable=no-member

    def assertNotAlmostEqual(self, *args, **kwargs):
        with breakOnError():
            super().assertNotAlmostEqual(*args, **kwargs)  # type: ignore # pylint: disable=no-member

    def assertGreater(self, *args, **kwargs):
        with breakOnError():
            super().assertGreater(*args, **kwargs)  # type: ignore # pylint: disable=no-member

    def assertGreaterEqual(self, *args, **kwargs):
        with breakOnError():
            super().assertGreaterEqual(*args, **kwargs)  # type: ignore # pylint: disable=no-member

    def assertLess(self, *args, **kwargs):
        with breakOnError():
            super().assertLess(*args, **kwargs)  # type: ignore # pylint: disable=no-member

    def assertLessEqual(self, *args, **kwargs):
        with breakOnError():
            super().assertLessEqual(*args, **kwargs)  # type: ignore # pylint: disable=no-member

    def assertRegex(self, *args, **kwargs):
        with breakOnError():
            super().assertRegex(*args, **kwargs)  # type: ignore # pylint: disable=no-member

    def assertNotRegex(self, *args, **kwargs):
        with breakOnError():
            super().assertNotRegex(*args, **kwargs)  # type: ignore # pylint: disable=no-member

    def assertCountEqual(self, *args, **kwargs):
        with breakOnError():
            super().assertCountEqual(*args, **kwargs)  # type: ignore # pylint: disable=no-member

    def fail(self, *args, **kwargs):
        with breakOnError():
            super().fail(*args, **kwargs)  # type: ignore # pylint: disable=no-member

    # Disable subTest functionality when doing parallel tests, as subTests cause a lot of issues with pickling when a
    # test fails, but only in parallel mode
    @contextmanager
    def subTest(self, *args, **kwargs):
        if settings.TEST_PARALLEL:
            logger.info(f"SUBTEST: {args}, {kwargs}")
            yield

        else:
            with super().subTest(*args, **kwargs):  # type: ignore # pylint: disable=no-member
                yield


class LiveServerMixin:
    """
    Overrides url settings to point live_server_url
    """

    def __init__(self, *args, **kwargs):
        # No restriction on length of diffs
        self.overrideSettingsCM = None
        super().__init__(*args, **kwargs)

    def setUp(self):
        self.overrideSettingsCM = override_settings(
            # SERVER_HOST=self.live_server_url,
            # SERVER_HOST_CA=self.live_server_url,
            # CALLBACK_HOST=self.live_server_url,
            # DIRECT_HOST=self.live_server_url,
            ## Add bold server to CORS whitelist
            # CORS_ALLOWED_ORIGINS=[
            #    *settings.CORS_ALLOWED_ORIGINS,
            #    f'http://127.0.0.1:{settings.BOLD_CASHIER_BOLDCOMMERCE_PORT + getTestThreadId()}',
            # ],
        )
        self.overrideSettingsCM.__enter__()  # pylint: disable=unnecessary-dunder-call
        super().setUp()  # type: ignore[misc]

    def tearDown(self):
        assert self.overrideSettingsCM is not None  # nosec: assert_used

        self.overrideSettingsCM.__exit__(*sys.exc_info())
        self.overrideSettingsCM = None
        super().tearDown()  # type: ignore[misc]


class OStaticLiveServerTestCase(
    LiveServerMixin,
    AssertHelper,
    ConfigMixin,
    TestTimingMixin,
    LogMonitorMixin,
    MemDebugMixin,
    StaticLiveServerTestCase,
):  # pylint: disable=too-many-ancestors
    pass


class OLiveServerTestCase(
    LiveServerMixin,
    AssertHelper,
    ConfigMixin,
    TestTimingMixin,
    LogMonitorMixin,
    MemDebugMixin,
    LiveServerTestCase,
):  # pylint: disable=too-many-ancestors
    pass


class OTestCase(
    AssertHelper,
    ConfigMixin,
    TestTimingMixin,
    LogMonitorMixin,
    MemDebugMixin,
    TestCase,
):  # pylint: disable=too-many-ancestors
    pass


class OTransactionTestCase(
    AssertHelper,
    ConfigMixin,
    TestTimingMixin,
    LogMonitorMixin,
    MemDebugMixin,
    TransactionTestCase,
):  # pylint: disable=too-many-ancestors
    pass
