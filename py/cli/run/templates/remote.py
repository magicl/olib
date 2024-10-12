# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~

import click

from ..utils.remote import con
from .base import prep_config


def _implement(plugins, default_host):
    @click.group(help='Remote commands')
    @click.option('-r', default=default_host, help='Remote target')
    @click.pass_context
    def remote_group(ctx, r):
        ctx.obj.meta.remote_target = r

    @remote_group.command(help='Ping')
    @click.pass_context
    def ping(ctx):
        data = con(ctx).gql_query('{ hello }')
        click.echo(data['hello'])

    @remote_group.command(help='Log in')
    @click.pass_context
    def login(ctx):
        con(ctx).token_save()

    @remote_group.command(help='Log out')
    @click.pass_context
    def logout(ctx):
        con(ctx).token_delete()

    @remote_group.command()
    @click.pass_context
    def show_logins(ctx):
        con(ctx).token_list()

    @remote_group.command()
    @click.pass_context
    def clear_logins(ctx):
        con(ctx).token_clear_all()

    # Read in remote command groups implemented across apps
    for plugin in plugins:
        for groupName, group in plugin():
            remote_group.add_command(group, name=groupName)

    return remote_group


def remote(
    plugins,
    hosts,
    default_host='local',
    token_file_path='~/.infrabase/secrets/remote_tokens',
):  # nosec: hardcoded_password_default

    def decorator(cls):
        prep_config(cls)

        cls.meta.remote_hosts = {h.name: h for h in hosts}
        cls.meta.remote_default_host = default_host
        cls.meta.remote_token_file_path = token_file_path

        cls.meta.commandGroups.append(('remote', _implement(plugins, default_host)))

        return cls

    return decorator
