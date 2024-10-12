# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Creates a hashed password based on a password string based on current settings'

    def add_arguments(self, parser):
        parser.add_argument('password', help='Password to hash')

    def handle(self, *args, **options):
        if not settings.DEBUG:
            return

        self.stdout.write(make_password(options['password']))
