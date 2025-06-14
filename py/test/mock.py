# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~

from typing import Any


class MockRequest:
    def __init__(self, user: Any = None, backend: str | None = None) -> None:
        self.user = user
        self.session: dict[str, Any] = {}
        self.META: dict[str, Any] = {}
        self.headers: dict[str, Any] = {}

        if user is not None:
            user.backend = backend if backend is not None else 'django.contrib.auth.backends.ModelBackend'

        # Attrnames to reset to when clearing
        self.attrNames = set(dir(self))
        self.attrNames.add('attrNames')
        # self.attrNames.add('foo') #Added as context below. Don't delete it

    # Stub functions required for Django's 'user_passes_test' as a part of testing viewAccess
    def build_absolute_uri(self) -> str:
        return ''

    def get_full_path(self) -> str:
        return ''

    def clearCachedData(self) -> None:
        """Go through and delete all attributes attached to request eby permission objects"""
        for name in dir(self):
            if name not in self.attrNames:
                delattr(self, name)
