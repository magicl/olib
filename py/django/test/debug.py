# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~
import inspect
import traceback
from contextlib import contextmanager

from django.conf import settings

_breakOnErrorEnabled = True


@contextmanager
def disableBreakOnError():
    global _breakOnErrorEnabled  # pylint: disable=global-statement

    old = _breakOnErrorEnabled
    _breakOnErrorEnabled = False
    try:
        yield
    except:  # Intentional bare-except, so pylint: disable=bare-except # nosec: try_except_pass
        pass

    _breakOnErrorEnabled = old


@contextmanager
def breakOnError():
    try:
        yield
    except:  # Intentional bare-except, so pylint: disable=bare-except
        if not breakOnErrorCheckpoint():
            raise


def breakOnErrorCheckpoint(exception: Exception | None = None, reason: str | None = None) -> bool:
    if not _breakOnErrorEnabled:
        return False

    ignoreError = False
    if settings.TEST_BREAK_ON_ERROR:
        ignoreBreak = False

        # If we are inside a waitfor, the allow it to fail, as this will simply make the waitFor continue waiting
        stack = inspect.stack()
        for frame in stack:
            if frame.function == 'waitFor' and frame.filename.endswith('tests/utils.py'):
                ignoreBreak = True
                break

        if not ignoreBreak:
            traceback.print_exc()
            if reason is not None:
                print(f"Reason: {reason}")
            breakpoint()  # pylint: disable=forgotten-debug-statement

    # To ignore error and continue, set ignoreError=True
    return ignoreError
