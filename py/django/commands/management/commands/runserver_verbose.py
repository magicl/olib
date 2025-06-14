# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~
import os
from typing import Any

from django.conf import settings
from django.core.management.commands.runserver import Command as RunserverCommand


class Command(RunserverCommand):
    def on_bind(self, server_port: Any) -> None:
        backend_host = getattr(settings, 'BACKEND_HOST', None)
        if backend_host is None:
            super().on_bind(server_port)
        else:
            print(f"Starting development server at {backend_host}/")
            print(f'  DEBUG:     {settings.DEBUG}')
            print(f'  LOG_LEVEL: {os.environ.get('LOG_LEVEL')}')
