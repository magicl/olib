# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~
import re
from collections.abc import Callable

from django.utils.functional import SimpleLazyObject, empty, lazy


class LazyRe(SimpleLazyObject):
    @property
    def wrapped(self):
        if self._wrapped is empty:  # type: ignore
            self._setup()  # type: ignore
        return self._wrapped  # type: ignore


def lazyReCompile(pattern: str | bytes, flags: int = 0) -> LazyRe:
    return LazyRe(lambda: re.compile(pattern, flags))


def lazySettingsStr(func: Callable) -> Callable:
    """Lazy string generation which is fed the django settings object. Evaluated on each invocation"""

    def wrap():
        from django.conf import settings

        return func(settings)

    return lazy(wrap, str)
