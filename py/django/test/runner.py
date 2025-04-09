# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~

import ctypes
import os
import re
import time
import unittest
from contextlib import contextmanager
from multiprocessing import (
    Manager,
    Pool,
    TimeoutError,
    Value,
    current_process,
    managers,
)
from typing import Any
from unittest import TestLoader

from django.conf import settings
from django.test.runner import DiscoverRunner, ParallelTestSuite, RemoteTestRunner
from rich.console import Console
from rich.table import Table

from olib.py.utils.mem import procMaxMemUsage

# Multiprocess data store. Don't create in daemonic processes
store: dict | managers.DictProxy

if not current_process().daemon:
    manager = Manager()
    store = manager.dict()
else:
    store = {}


def get_test_thread_id():
    """When using multiple test threads, gives the ID of the current thread"""
    # Get ID from current db. dbname is suffixed by a number for each
    # thread after the first thread
    dbname = settings.DATABASES['default']['NAME']
    split = dbname.rsplit('_', 1)[1]
    try:
        return 0 if split in ['test', 'dev'] else int(split)
    except ValueError:
        return 0  # Could not get index from database name


def getTestSettingsName():
    """Returns settings name for test that also includes multiprocessing ID"""
    return f"{settings.SETTINGS_NAME}*{get_test_thread_id()}"


class OTextResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Only set for parallel tests
        self.xTestThreadId = None

    def setCustomInfo(self, test, testThreadId):
        self.xTestThreadId = testThreadId

    def startTest(self, test):
        testName = f"::{test.__class__.__module__}.{test.__class__.__name__}.{test._testMethodName} "  # pylint: disable=protected-access
        self.stream.write(f"{testName:.<120}")
        self.stream.flush()

        super().startTest(test)

    # def _print_unpicklable_subtest(self, test, subtest, pickle_exc):
    #    print('PICKLE OVERRIDE')
    #    super()._print_unpicklable_subtest(self, test, subtest, pickle_exc)

    def addSuccess(self, test):
        from olib.py.django.test.cases import (
            OLiveServerTestCase,
            OStaticLiveServerTestCase,
            OTransactionTestCase,
        )

        super().addSuccess(test)

        mStr = ''
        tStr = ''
        if test.tTestStart:
            # Not recorded in parallel mode
            end = time.time()
            # durationTest = round(end - self.tStartTest, 2)
            # durationReal = round(end - self.tStartReal, 2)
            # import ipdb; ipdb.set_trace() #why below not working?
            test.tTest = end - test.tTestStart
            test.tReal = end - test.tRealStart
            test.mRssMaxPost = procMaxMemUsage()

            tExtraStr = ''
            # print(dir(test))
            # print(vars(test))
            if test.prevTest is not None:
                # Calculate additional time spend for previous test, not captured with current timers
                tExtra = test.tRealStart - test.prevTest.tRealStart - test.prevTest.tReal
                tExtraStr = f" +{tExtra:4.03f}"

            tStr = f" {test.tTest:4.03f}...{test.tReal:4.03f} {tExtraStr}"

            if test.mRssMaxPost > test.mRssMaxPre:
                mStr = f" {round(test.mRssMaxPost)} MB"

        testType = (
            '**'
            if isinstance(test, (OStaticLiveServerTestCase, OLiveServerTestCase))
            else '*' if isinstance(test, OTransactionTestCase) else ''
        )

        threadStr = f" @{self.xTestThreadId}" if self.xTestThreadId is not None else ''

        self.stream.writeln(f"{'ok':.>6}{tStr} {testType}{mStr}{threadStr}")  # type: ignore[attr-defined]

    def addError(self, test, err):
        super().addError(test, err)
        self.stream.writeln(f"{'ERROR':.>6}")  # type: ignore[attr-defined]

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self.stream.writeln(f"{'FAIL':.>6}")  # type: ignore[attr-defined]

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self.stream.writeln(f"{'skip!':.>6}")  # type: ignore[attr-defined]


class OTextTestRunner(unittest.TextTestRunner):
    resultclass = OTextResult


# class ORemoteTestResult(RemoteTestResult):
#     pass


class ORemoteTestRunner(RemoteTestRunner):
    # resultclass = ORemoteTestResult

    def run(self, test):
        result = super().run(test)

        # Prepend event with additional data to help pass down which thread ran this test
        result.events.insert(0, ('setCustomInfo', result.test_index, get_test_thread_id()))

        return result


class OParallelTestSuite(ParallelTestSuite):
    runner_class = ORemoteTestRunner

    def run(self, result):
        """
        Lifted from Django to replace pool.close with pool.terminate on StopIteration to make sure
        mockserver threads don't prevent test suite from stopping
        """

        self.initialize_suite()
        counter = Value(ctypes.c_int, 0)
        pool = Pool(  # pylint: disable=consider-using-with
            processes=self.processes,
            initializer=self.init_worker.__func__,
            initargs=[
                counter,
                self.initial_settings,
                self.serialized_contents,
                self.process_setup.__func__,
                self.process_setup_args,
                self.debug_mode,
            ],
        )
        args = [
            (self.runner_class, index, subsuite, self.failfast, self.buffer)
            for index, subsuite in enumerate(self.subsuites)
        ]
        test_results = pool.imap_unordered(self.run_subsuite.__func__, args)

        while True:
            if result.shouldStop:
                pool.terminate()
                break

            try:
                subsuite_index, events = test_results.next(timeout=0.1)
            except TimeoutError:
                continue
            except StopIteration:
                # pool.close()
                pool.terminate()  # <---- EDIT to force close even if threads are stuck
                break

            tests = list(self.subsuites[subsuite_index])
            for event in events:
                event_name = event[0]
                handler = getattr(result, event_name, None)
                if handler is None:
                    continue
                test = tests[event[1]]
                args = event[2:]
                handler(test, *args)

        pool.join()

        return result


class OTestLoader(TestLoader):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.exclude_dir_regexp = ''

    def _find_tests(self, start_dir, pattern):
        if self.exclude_dir_regexp and re.search(self.exclude_dir_regexp, start_dir):
            return

        yield from super()._find_tests(start_dir, pattern)  # type: ignore[misc]


# Custom runner
class OTestRunner(DiscoverRunner):
    """
    Provides additional benefits over Django's runner:
    * Can completely ignore database creation, which is used in 'scripts/test-old-code-new-db.py'
    * Can provide testcase name as context to tests, to help identify which test an error comes from
    * Times individual tests and measures memory consumption
    """

    test_runner = OTextTestRunner
    test_loader = OTestLoader()
    parallel_test_suite = OParallelTestSuite

    def __init__(
        self,
        keepdb_hard=False,
        test_name_patterns=None,
        exclude_dir_regexp='',
        **kwargs,
    ):

        if settings.TEST_RUN_FAILED:
            # Read and add tests failed in past iteration to run-list
            try:
                with open('.output/failed-tests.txt', encoding='utf-8') as f:
                    failedTestsOutput = f.read()

                if not failedTestsOutput:
                    failedTestsOutput = 'dont-match-with-any-tests--all-tests-are-ok'

                # Add a * to the beginning of the paths to prevent DiscoverRunner from adding it to the front and back of the patterns
                test_name_patterns = (test_name_patterns or []) + [
                    '*' + v.strip() for v in failedTestsOutput.split(' ')
                ]

            except FileNotFoundError:
                pass  # No failed-tests file found. Continue and run full test

        if (tp := kwargs['pattern']) != 'test*.py' and tp[0] != '*' and not tp.endswith('*.py'):
            # Help out by wrapping test pattern.. In this way, test can be run with `-p foo` and it will be translated to `-p *foo*py
            kwargs['pattern'] = f"test*{tp}*.py"

        super().__init__(test_name_patterns=test_name_patterns, **kwargs)
        self.keepdb_hard = keepdb_hard
        self.result = None

        self.test_loader.exclude_dir_regexp = exclude_dir_regexp

        os.environ['TESTING_TEST_ARG'] = 'testing!'

    @classmethod
    def add_arguments(cls, parser):
        super().add_arguments(parser)

        parser.add_argument(
            '--keepdb-hard',
            action='store_true',
            dest='keepdb_hard',
            default=False,
            help='Will prevent any modification of db during test startup. Stronger guarantee than --keepdb',
        )
        parser.add_argument(
            '--exclude-dir-regexp',
            type=str,
            default='',
            help='Exclude any test module containing this string',
        )

        # Currently only for documentation purposes. Settings is read before testrunner, so currently have no way of injecting these into the
        # individual tests. Actual implementation is in olib.py.django.app.settingsbase
        parser.add_argument(
            '--selenium-gui',
            action='store_true',
            default=False,
            help='Enable selenium GUI',
        )
        parser.add_argument(
            '--selenium-devtools',
            action='store_true',
            default=False,
            help='Enable selenium GUI chrome dev-tools',
        )
        parser.add_argument(
            '--selenium-maximized',
            action='store_true',
            default=False,
            help='Start GUI in maximized mode',
        )
        parser.add_argument(
            '--selenium-timeouts-disable',
            action='store_true',
            default=False,
            help='Disable selenium timeouts',
        )
        parser.add_argument(
            '--selenium-dly',
            type=int,
            default=0,
            help='Add delays, slowing down selenium actions',
        )

        parser.add_argument(
            '--unsuppress-log',
            action='store_true',
            default=False,
            help='Disable log suppression to see what is suppressed',
        )
        parser.add_argument(
            '--break-on-error',
            action='store_true',
            default=False,
            help='Enter debugger on waitFor fail',
        )
        parser.add_argument(
            '--debug-mem',
            action='store_true',
            default=False,
            help='Debug memory consumption in testcases',
        )
        parser.add_argument('--test-db', type=int, default=0, help='Specify test database')

        parser.add_argument(
            '--mvt',
            action='store_true',
            default=False,
            help='Reduce test-set to minimum viable',
        )
        parser.add_argument('--live', action='store_true', default=False, help='Run live tests only')
        parser.add_argument(
            '--live-prod',
            action='store_true',
            default=False,
            help='Run reduced live tests on production',
        )
        parser.add_argument(
            '--live-reduced',
            action='store_true',
            default=False,
            help='Run reduced live tests on staging',
        )
        parser.add_argument('--public', action='store_true', default=False, help='Enable public tests')
        parser.add_argument(
            '--failed',
            action='store_true',
            default=False,
            help='Run tests failed in previous run',
        )

        parser.add_argument(
            '--repr-log',
            action='store_true',
            default=False,
            help='Make log more reproducible by removing timings, etc. Helps with log diffs between succeeding and failing tests',
        )

    def run_tests(self, *args, **kwargs):  # pylint: disable=signature-differs
        # from tests.selenium.selenium_browsers import SeleniumBrowser
        ret = super().run_tests(*args, **kwargs)

        assert self.result is not None  # nosec: assert_used

        # Kill any selenium instances that might still be running
        # SeleniumBrowser.quit()

        # Print aggregate results
        timingRows = []
        for k, v in store.items():
            if k.startswith('timing|'):
                name = k[7:]
                timingRows.append([name, str(round(v, 3)), str(store[f"calls|{name}"])])

        if timingRows:
            console = Console(record=True)
            table = Table()
            columns: list[tuple[str, dict[str, Any]]] = [
                ('Name', {}),
                ('Time', {'justify': 'right'}),
                ('Calls', {'justify': 'right'}),
            ]
            for col, colArgs in columns:
                table.add_column(col, **colArgs)

            for row in timingRows:
                table.add_row(*row)

            console.print('\nAggregate timings:')
            console.print(table)

            # table = tt.Texttable(max_width=240)
            # table.add_rows([['Name', 'Time', 'Calls'], *timingRows])
            # print(f'\nAggregate timings:\n{table.draw()}')

        # Print all failed tests
        failedTests = [r[0] for r in self.result.errors or []] + [r[0] for r in self.result.failures]
        if failedTests:
            # Resolve subtests and remove duplicates
            failedTests = [f.test_case if isinstance(f, unittest.case._SubTest) else f for f in failedTests]  # type: ignore[attr-defined] # pylint: disable=protected-access
            failedTestsOutput = ' '.join(
                f"{test.__class__.__module__}.{test.__class__.__name__}.{test._testMethodName}"  # pylint: disable=protected-access
                for test in set(failedTests)
                # pylint: disable=protected-access
                if not isinstance(test, unittest.suite._ErrorHolder)  # type: ignore[attr-defined]
                # pylint: enable=protected-access
            )

            print(f"\nFailed Tests:\n{failedTestsOutput}")

        else:
            failedTestsOutput = ''

        os.makedirs('.output', exist_ok=True)
        with open('.output/failed-tests.txt', 'w', encoding='utf-8') as f:
            f.write(failedTestsOutput)

        return ret

    def suite_result(self, suite, result, **kwargs):
        """Default django version converts result to simply an integer number of failures.. Capture results as sell"""
        self.result = result

        return super().suite_result(suite, result, **kwargs)

    def setup_databases(self, *args, **kwargs):
        """Preload fixtures once for all testcases"""

        if self.keepdb_hard:
            return None

        ret = super().setup_databases(*args, **kwargs)
        if not ret:
            # No database set up. No need to initialize
            return ret

        return ret

    def teardown_databases(self, old_config, **kwargs):
        if self.keepdb_hard:
            return

        super().teardown_databases(old_config, **kwargs)


# Utilities
@contextmanager
def measure_runtime(name):
    t = time.time()
    yield
    key = f"timing|{name}"
    t = time.time() - t

    if key not in store:
        store[key] = t
    else:
        store[key] += t

    key = f"calls|{name}"
    if key not in store:
        store[key] = 1
    else:
        store[key] += 1
