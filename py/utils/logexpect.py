# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~

import logging
import re
import time
import uuid
from collections.abc import Generator
from contextlib import contextmanager
from inspect import Traceback, getframeinfo, stack
from multiprocessing import Manager, current_process, managers
from typing import cast

from django.conf import settings

from olib.py.utils.execenv import isEnvTest
from olib.py.utils.lazy import lazyReCompile

logger = logging.getLogger('utils.logexpect')

errorReg = lazyReCompile('ERROR|error|Error|Exception|EXCEPTION|exception|Traceback.*')

# Multiprocess data store. Don't create in daemonic processes. Also only needed in test environment
store: dict[str, int | str] | managers.DictProxy  # type: ignore
if not current_process().daemon and isEnvTest():
    manager = Manager()
    store = manager.dict()
else:
    store = {}


def storeSet(key: str, val: int | str) -> None:
    store[key] = val
    # print(f'set: {key}, {val} -> {os.getpid()}.{threading.get_ident()}.{id(store)}\n{pprint.pformat(store)}')


def storeAdd(key: str, val: int) -> None:
    # print(f'add: {key}, {val} -> {id(store)} TRY')
    if key not in store:
        store[key] = val
        # print(f'add: {key}, {val} -> {os.getpid()}.{threading.get_ident()}.{id(store)}\n{pprint.pformat(store)}')


def storeDec(key: str, val: int = 1) -> int:
    store[key] -= val  # type: ignore
    # print(f'dec: {key}, {val} -> {os.getpid()}.{threading.get_ident()}.{id(store)}\n{pprint.pformat(store)}')
    return store[key]  # type: ignore


class ExpectLogItem(logging.Filter):
    postfixCounter = 0  # Added to keys to prevent items created rapidly after eachother from getting the same ID

    def __init__(self, logger_: str, level: int, regex: str, count: int = 1, suppress: bool = True) -> None:
        """
        :params count: set to -1 to block messages without a count cap
        """
        super().__init__()

        self.logger = logger_
        self.level = level
        self.regex = regex
        self.cRegex = re.compile(regex, re.DOTALL | re.M)
        self.suppress = suppress
        self.initialCount = count
        self.countId = ''
        self.callerInfo = ''  # Info about where in code this log expectation is
        self.logDataId = ''

    def init(self, caller: Traceback | None = None) -> None:
        """Separate init function so object can be re-used multiple times"""
        # Items will be used across threads in a given process. Use regex and test-thread id to create
        # a unique entry in dict. Then use this value to keep track of number of hits
        self.countId = f'expect-log:{uuid.uuid1()}:{ExpectLogItem.postfixCounter}'
        self.logDataId = f'expect-log-data:{uuid.uuid1()}:{ExpectLogItem.postfixCounter}'
        self.callerInfo = f' ({caller.filename}:{caller.lineno}) ' if caller else ''
        # logger.info('creating key {}'.format(self.countId))
        storeAdd(self.countId, self.initialCount)
        storeSet(self.logDataId, '')
        ExpectLogItem.postfixCounter += 1

    def filter(self, record: logging.LogRecord) -> bool:
        # If record has exception attached, add exception info to match so we can filter on exception info
        message = record.getMessage()
        if record.exc_info:
            message += '. ' + str(record.exc_info[1])

        # if self.cRegex.match(message):
        # logger.info('level: {} == {}, {} on "{}" ~= "{}" at count={} countId {}'.format(record.levelno, self.level, self.cRegex.match(message) is not None, self.regex, message, self.count(), self.countId))

        if not isinstance(record.msg, str):
            # Don't process non-string messages
            return True

        msg = str(message)
        match = record.levelno == self.level and self.cRegex.search(msg)

        if match:
            # We have a match. Log it
            # self.logRecord('  MATCH: ', record)

            if self.initialCount >= 0:
                try:
                    count = storeDec(self.countId)
                except ValueError:
                    logging.error(f'unable to suppress hit to {self.countId}')
                    return False  # Don't suppress

                if count < 0:
                    logger.error(f'Got more than expected matches of log message{self.callerInfo}`{msg}`')
                    return True  # Let it through. Not supposed to catch it

                if settings.TEST_UNSUPPRESS_LOG:
                    # Do not suppress log message, but rather redact items that would be an issue
                    if self.suppress:
                        record.levelno = logging.DEBUG
                        record.levelname = 'SUP!!'
                        record.msg = cast(re.Pattern[str], errorReg).sub(
                            lambda m: m.group(0)[:2] + ('*' * (len(m.group(0)) - 4)) + m.group(0)[-2:], record.msg
                        )
                    return True

                return not self.suppress  # Filter it

            # Negative initial count, let any number through, while suppressing
            return False

        # No match. Let it pass
        record.msg = '[SEEN->] ' + record.msg + ' [<-SEEN]'
        return True

    def count(self) -> int:
        # logger.info('using key {}'.format(self.countId))
        return cast(int, store.get(self.countId, 0))

    def wait(self, timeout: float = 10) -> None:
        """Wait until expected log messages have been received"""
        tStart = time.time()
        while self.count() > 0 and time.time() - tStart < timeout:
            time.sleep(0.1)

        if self.count() > 0:
            raise Exception('Log messages not seen before timeout')

    def records(self) -> str:
        return cast(str, store.get(self.logDataId))

    def __str__(self) -> str:
        return f'logger: {self.logger}, level: {self.level}, regex: {self.regex}'


# Checks for a specific number of defined log messages, and by default also suppresses them
@contextmanager
def expectLogItems(items: list[ExpectLogItem]) -> Generator[list[ExpectLogItem], None, None]:
    # Get info about caller so we can give better error messages
    # 0 is logging.expectLogItems
    # 1 is contextlib.__enter__
    # 2 is caller
    caller = getframeinfo(stack()[2][0])

    # Apply log filters
    for i in items:
        # Verify that specified logger has been registered
        loggerInst = logging.root.manager.loggerDict.get(i.logger)  # pylint: disable=no-member
        if not loggerInst or not isinstance(loggerInst, logging.Logger):
            raise ValueError(f'Logger {i.logger} not registered')

        i.init(caller)
        # logging.getLogger(i.logger).addFilter(i)
        loggerInst.addFilter(i)

    try:
        # Run stuff
        yield items
    finally:
        # Remove log filters
        for i in items:
            logging.getLogger(i.logger).removeFilter(i)

            # Verify that all items were hit
            if i.count() > 0:
                logger.error(
                    f'Logging {i.callerInfo} expected to be hit {i.count()} more times. {i}. Seen items:{i.records()}'
                )
