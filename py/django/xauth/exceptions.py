# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~

import logging

from django.conf import settings
from django.core.exceptions import PermissionDenied

logger = logging.getLogger(__name__)


class PermissionException(PermissionDenied):
    """On production, limits error information to a minimum"""

    def __init__(self, msg, *args, **kwargs):
        logger.info(f"PermissionException: {msg}")

        if not getattr(settings, 'XAUTH_EXPOSE_VERBOSE_ERRORS', settings.DEBUG):
            msg = 'Access Denied'

        super().__init__(msg, *args, **kwargs)


class PermissionConfigurationException(PermissionException):
    pass
