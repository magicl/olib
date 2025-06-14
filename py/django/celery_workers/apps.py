# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~

from django.apps import AppConfig
from django.core import checks

from .checks import checkSettings


class CeleryWorkersConfig(AppConfig):
    name = 'olib.py.django.celery_workers'
    verbose_name = 'Celery Workers'

    def ready(self) -> None:
        checks.register(checkSettings)
