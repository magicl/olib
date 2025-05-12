# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~
import logging
import time
from collections.abc import Callable
from typing import Any

from olib.py.django.test.debug import breakOnError

logger = logging.getLogger(__name__)


class WaitForException(Exception):
    pass


def waitFor(
    func: Callable,
    *,
    equals: Any | None = None,
    condition: Callable | None = None,
    timeout: int = 10,
    extraDelay: Any | None = None,
    delay: float = 0.1,
    info: Callable | str = '',
    raiseOnFailure: bool = True,
    description: str = '',
) -> Any:
    """Waits until func returns True. Ok for function to raise in waiting period"""
    logger.info(f"waitfor start: {description}")
    # timeout = timeout #if not settings.TEST_SELENIUM_TIMEOUT_DISABLE else 36000
    start = time.time()
    exception = None
    ret = None
    while time.time() - start < timeout:
        try:
            ret = func()
            # logger.info(f' test value: {ret}')
        except Exception as e:  # pylint: disable=broad-exception-caught
            exception = e
            # logger.info(f' test value: {e}')
        else:
            if callable(condition):
                acceptable = condition(ret)
            elif equals is not None:
                acceptable = ret == equals
            else:
                acceptable = bool(ret)

            if acceptable:
                # Success
                exception = None  # Ok to have had exceptions during wait if eventually resolves to ok
                logger.info('waitfor success!')
                if extraDelay:
                    time.sleep(extraDelay)
                return ret

    if raiseOnFailure:
        with breakOnError():
            if exception is not None:
                raise exception  # pylint: disable=raising-bad-type # pylint thinks this is still None

            _info = info if isinstance(info, str) else info()
            if equals:
                raise WaitForException(f"function never returned correct value, {ret} != {equals}: {_info}")

            raise WaitForException(f"function never returned True: {_info}")

    return None
