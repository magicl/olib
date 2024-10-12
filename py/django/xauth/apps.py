# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~

from django.apps import AppConfig


class XAuthConfig(AppConfig):
    name = 'olib.py.django.xauth'
    verbose_name = 'Authentication / Authorization'

    def ready(self):
        from olib.py.django.xauth.monkeypatches import applyMonkeyPatches

        applyMonkeyPatches()
