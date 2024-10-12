# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~

import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
os.environ['PYTHONPATH'] = ':'.join(sys.path)

from olib.py.cli.run.templates import django, mysql, postgres, redis


@mysql(root=True)
@postgres(root=True)
@redis(root=True)
@django(settings='olib.py.django._app.settings', manage_py='py/django/_app/manage.py', django_working_dir='.')
class Config:
    displayName = 'OLIB'
    clusters = None
    tools = ['python']
