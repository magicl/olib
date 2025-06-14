# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~
import os
from typing import Any

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Creates an admin user non-interactively if it doesn't exist, but only if DEBUG=True"

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument('--username', help="Admin's username")
        parser.add_argument('--email', help="Admin's email")
        parser.add_argument('--password', help="Admin's password")
        parser.add_argument('--no-input', help='Read options from the environment', action='store_true')

    def handle(self, *args: Any, **options: Any) -> None:
        if not settings.DEBUG:
            return

        # time_start = time.time()

        User = get_user_model()

        if options['no_input']:
            options['username'] = os.environ['DJANGO_SUPERUSER_USERNAME']
            options['email'] = os.environ['DJANGO_SUPERUSER_EMAIL']
            options['password'] = os.environ['DJANGO_SUPERUSER_PASSWORD']

        if not User.objects.filter(username=options['username']).exists():
            User.objects.create_superuser(
                username=options['username'], email=options['email'], password=options['password']
            )

        # time_end = time.time()
        # print(f'... done in {time_end - time_start:.2f} seconds')
