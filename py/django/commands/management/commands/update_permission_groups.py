# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand

from django.contrib.auth.models import Group, Permission
from django.db import transaction
import json


class Command(BaseCommand):
    help = 'Creates a hashed password based on a password string based on current settings'

    def add_arguments(self, parser):
        parser.add_argument('file', help='JSON file with permission groups')

    def handle(self, *args, **options):

        with open(options['file'], 'r') as f:
            permission_groups = json.load(f)


        group_defs = permission_groups['groups']

        with transaction.atomic():
            #Delete missing groups
            Group.objects.exclude(name__in=[group_def['name'] for group_def in group_defs]).delete()

            #Create and update groups
            for group_def in group_defs:
                group, _ = Group.objects.get_or_create(name=group_def['name'])

                permissions = []
                for perm_spec in group_def['permissions']:
                    app_label, codename = perm_spec.split('.')
                    perm = Permission.objects.filter(codename=codename, content_type__app_label=app_label).first()

                    if perm is None:
                        raise Exception(f'Permission {perm_spec} not found')
                    
                    permissions.append(perm)

                group.permissions.set(permissions)



