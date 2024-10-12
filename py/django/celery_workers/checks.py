# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~

from django.conf import settings
from django.core import checks


def checkSettings(**kwargs):
    """Verify settings required by app"""
    errors = []

    if not hasattr(settings, 'CELERY_WORKERS_BROKER_URL'):
        errors.append(checks.Error('CELERY_WORKERS_BROKER_URL must be defined for celery_workers app'))
    if not hasattr(settings, 'CELERY_WORKERS_RESULT_BACKEND'):
        errors.append(checks.Error('CELERY_WORKERS_RESULT_BACKEND must be defined for celery_workers app'))

    return errors
