# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~

from django.apps import AppConfig
from django.conf import settings


class ConfConfig(AppConfig):
    name = 'olib.py.django.conf'
    verbose_name = 'Config'

    def ready(self):
        # Register base settings from app.
        from olib.py.django.conf.osettings import osettings

        for spec in getattr(settings, 'CONF_OSETTINGS', []):
            osettings.register(**spec)
