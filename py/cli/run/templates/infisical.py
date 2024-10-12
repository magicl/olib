# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~

import click

from ....utils.kubernetes import (
    k8s_namespace_create,
    k8s_secret_create,
    k8s_secret_delete,
)
from ..utils.infisical import infisical_convert_name, infisical_creds
from .base import prep_config


def _implement():
    @click.group()
    def infisicalGroup(help='Infisical commands'):
        pass

    @infisicalGroup.command()
    @click.pass_context
    def app_create(ctx):
        """Copy infisical secret into namespace"""
        secret_name = infisical_convert_name(ctx)
        client_id, client_secret = infisical_creds(ctx)

        # Create a kubernetes secret for infisical in the target namespace
        k8s_namespace_create(ctx.obj.k8sNamespace, ctx.obj.k8sContext)

        k8s_secret_create(
            secret_name,
            ctx.obj.k8sNamespace,
            ctx.obj.k8sContext,
            {
                'clientId': client_id,
                'clientSecret': client_secret,
            },
        )
        click.echo('Added infisical secret to kubernetes')

    @infisicalGroup.command()
    @click.pass_context
    def app_delete(ctx):
        """Remove infisical secret from namespace"""
        secret_name = infisical_convert_name(ctx)

        # Delete kubernetes secret
        k8s_secret_delete(secret_name, ctx.obj.k8sNamespace, ctx.obj.k8sContext)
        click.echo('Deleted infisical secret from kubernetes')

    return infisicalGroup


def infisical():
    """
    Injects functions into service Config for managing infisical

    Expects:

    """

    def decorator(cls):
        prep_config(cls)

        cls.meta.commandGroups.append(('infisical', _implement()))

        return cls

    return decorator
