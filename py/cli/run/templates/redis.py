# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~

# pylint: disable=duplicate-code

import click
import sh

from ....utils.kubernetes import (
    k8s_namespace_create,
    k8s_secret_create,
    k8s_secret_delete,
)
from ..utils.redis_utils import redis_convert_name, redis_creds, redis_port_forward
from .base import prep_config


def _implement(defaultRoot=True):
    @click.group()
    def redisGroup(help='Redis commands'):
        pass

    @redisGroup.command(help='Start a Redis shell')
    @click.option('--root', help='Start in root mode', default=False, is_flag=True)
    @click.pass_context
    def shell(ctx, root):
        pwd, database = redis_creds(ctx, root or defaultRoot)

        with redis_port_forward() as port:
            args = ['-h', '127.0.0.1', '-p', port]
            if database is not None:
                args += ['-n', database]

            sh.Command('redis-cli')(*args, _fg=True, _env={'REDISCLI_AUTH': pwd})

    if not defaultRoot:

        @redisGroup.command()
        @click.pass_context
        def app_create(ctx):
            """Copy redis secret into namespace"""
            secretName, *_ = redis_convert_name(ctx)
            password, _ = redis_creds(ctx, defaultRoot)

            # Create a kubernetes secret for redis in the target namespace
            k8s_namespace_create(ctx.obj.k8sNamespace, ctx.obj.k8sContext)

            k8s_secret_create(
                secretName,
                ctx.obj.k8sNamespace,
                ctx.obj.k8sContext,
                {
                    'password': password,
                },
            )
            click.echo('Added redis secret to kubernetes')

        @redisGroup.command()
        @click.pass_context
        def app_delete(ctx):
            """Remove redis secret from namespace"""
            secretName, *_ = redis_convert_name(ctx)

            # Delete kubernetes secret
            k8s_secret_delete(secretName, ctx.obj.k8sNamespace, ctx.obj.k8sContext)
            click.echo('Deleted redis secret from kubernetes')

    return redisGroup


def redis(root=False):
    """
    Injects functions into service Config for managing redis

    Expects:

    """

    def decorator(cls):
        prep_config(cls)

        cls.meta.redis = True

        cls.meta.commandGroups.append(('redis', _implement(root)))

        return cls

    return decorator
