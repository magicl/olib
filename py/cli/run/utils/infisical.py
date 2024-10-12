# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~

import sys

import click

from ....utils.clients.infisical import Infisical
from ....utils.secrets import readFileSecretSplit


def infisical_convert_name(ctx):
    name = ctx.obj.k8sAppName

    if any(name.startswith(prefix) for prefix in ['root', 'localroot', 'infisical']):
        click.echo(f'The following name is reserved: "{name}"')
        sys.exit(1)

    secret_name = (
        'infisical'  # secret_name excludes 'name' so it can be referenced easily in kubernetes templates  # nosec
    )

    return secret_name


def infisical_creds(ctx) -> tuple[str, str]:
    """Returns client_id, client_secret. Invalidates previous client_secret"""
    cli_client_id, cli_client_secret = readFileSecretSplit('~/.infrabase/secrets/infra/infisical-cli.txt')

    return Infisical(client_id=cli_client_id, client_secret=cli_client_secret).create_client_secret(
        ctx.obj.inst['infisical_identity_id'], ctx.obj.inst['name']
    )
