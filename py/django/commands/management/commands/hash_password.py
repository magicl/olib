# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Updates permission groups based on a JSON file'

    def add_arguments(self, parser):
        parser.add_argument('password', help='Password to hash')

    def handle(self, *args, **options):
        


        self.stdout.write(make_password(options['password']))
