# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~

import os
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from olib.py.cli.run.utils.remote import RemoteHost


class ConfigMeta:
    commandGroups: list[tuple[str, Any]] = []

    # Environment
    isOlib = os.path.exists('.is_olib')
    olib_path = os.environ['OLIB_PATH']

    # Options
    django = False
    django_settings: str | None = None

    # Remote
    remote_target: str | None = None  # Set by 'remote' command group
    remote_hosts: dict[str, 'RemoteHost'] = {}
    remote_default_host: str | None = None

    # Databases
    mysql = False
    postgres = False
    redis = False

    def __init__(self, command_groups=None):
        self.commandGroups = command_groups or []


def prep_config(config):
    if not hasattr(config, 'meta'):
        config.meta = ConfigMeta()
