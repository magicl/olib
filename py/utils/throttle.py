# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~

import time
from collections.abc import Callable
from typing import Any


class BackoffFailedException(Exception):
    pass


def exponentialBackoff(
    func: Callable[[], Any],
    exCheckFunc: Callable[[Exception], bool] | None = None,
    maxRetries: int = 8,
    initialDelaySeconds: float = 1,
    maxDelaySeconds: float = 60,
    retryOnFalse: bool = False,
) -> Any:
    """
    Implements exponential backoff, which is useful when dealing with throttling. Backoff is not randomized.
    :param func:         Function to call, which can be throttled
    :param exCheckFunc:  If an exception happens during execution of func, exCheckFunc is passed the exception, and returns true to try again with backup, or false to re-raise
    """
    delay = initialDelaySeconds
    retries = 0

    while True:
        try:
            val = func()
            if not retryOnFalse or val:
                return val

        except Exception as e:  # pylint: disable=broad-exception-caught
            if exCheckFunc is None or not exCheckFunc(e):
                raise

        if retries >= maxRetries:
            raise BackoffFailedException()

        # Apply exponential backup and try again
        time.sleep(delay)
        delay = min(delay * 2, maxDelaySeconds)
        retries += 1
