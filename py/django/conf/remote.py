# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~

from typing import Any

import click

from olib.py.cli.run.utils.remote import con


def conf_cli() -> list[tuple[str, Any]]:
    """Remote CLI for app"""

    @click.group(name='os', help='Online Settings')
    def os_group() -> None:
        pass

    @os_group.command('list', help='List all online settings with data')
    @click.pass_context
    def list(ctx) -> None:
        con(ctx).gql_query('{ onlineSettings { edges { node { name type value } } } }')
        breakpoint()  # pylint: disable=forgotten-debug-statement
        print('foo')
        # NOTE: Create common function that outputs table with default columns, an dhas cli arg to add additional columns (like the kubectl commands)

    @os_group.command('set')
    @click.argument('name', type=str)
    @click.argument('value', type=str)
    @click.pass_context
    def update(ctx, name: str, value: str) -> None:
        con(ctx).gql_mut('onlineSettingUpdate', name=name, value=value)

    return [('os', os_group)]
