# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~
import logging
import threading
from typing import Any

from decorator import decorator

logger = logging.getLogger(__name__)


@decorator
def synchronized(wrapped: Any, instance: Any, *args: Any, **kwargs: Any) -> Any:
    """
    Apply synchronization to class function or stand-alone function
    From https://github.com/GrahamDumpleton/wrapt/blob/develop/blog/07-the-missing-synchronized-decorator.md
    """
    if instance is None:
        owner = wrapped
    else:
        owner = instance

    lock = vars(owner).get('_synchronized_lock', None)

    if lock is None:
        meta_lock = vars(synchronized).setdefault('_synchronized_meta_lock', threading.Lock())

        with meta_lock:
            lock = vars(owner).get('_synchronized_lock', None)
            if lock is None:
                lock = threading.RLock()
                setattr(owner, '_synchronized_lock', lock)

    with lock:
        ret = wrapped(instance, *args, **kwargs)
        return ret
