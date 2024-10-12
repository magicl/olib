# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~


class MockRequest:
    def __init__(self, user=None, backend=None):
        self.user = user
        self.session = {}
        self.META = {}
        self.headers = {}

        if user is not None:
            user.backend = backend if backend is not None else 'django.contrib.auth.backends.ModelBackend'

        # Attrnames to reset to when clearing
        self.attrNames = set(dir(self))
        self.attrNames.add('attrNames')
        # self.attrNames.add('foo') #Added as context below. Don't delete it

    # Stub functions required for Django's 'user_passes_test' as a part of testing viewAccess
    def build_absolute_uri(self):
        return ''

    def get_full_path(self):
        return ''

    def clearCachedData(self):
        """Go through and delete all attributes attached to request eby permission objects"""
        for name in dir(self):
            if name not in self.attrNames:
                delattr(self, name)
