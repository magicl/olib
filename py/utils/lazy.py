# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~
import re

from django.utils.functional import SimpleLazyObject, empty, lazy


class LazyRe(SimpleLazyObject):
    @property
    def wrapped(self):
        if self._wrapped is empty:
            self._setup()
        return self._wrapped


def lazyReCompile(pattern: str | bytes, flags: int = 0):
    return LazyRe(lambda: re.compile(pattern, flags))


def lazySettingsStr(func):
    """Lazy string generation which is fed the django settings object. Evaluated on each invocation"""

    def wrap():
        from django.conf import settings

        return func(settings)

    return lazy(wrap, str)
