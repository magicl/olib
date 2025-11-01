# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~

# Shares a lot of code with postgres template
# pylint: disable=duplicate-code

import sys
from contextlib import nullcontext
from functools import partial
from typing import Any

import click
import sh

from ....utils.kubernetes import (
    k8s_namespace_create,
    k8s_secret_create,
    k8s_secret_delete,
    k8s_secret_exists,
    k8s_secret_read_single,
)
from ....utils.passwords import makePassword
from ..utils.mysql import (
    mysql_connect,
    mysql_convert_name,
    mysql_pipe,
    mysql_query,
    mysql_shell_connect_args,
    mysqlsh_shell_connect_args,
)
from ..utils.mysql_backup import mysql_backup_import
from .base import prep_config


def _implement(defaultRoot: bool = True) -> Any:
    @click.group(help='MySQL commands')
    def mysqlGroup() -> None:
        pass

    @mysqlGroup.command(help='Start a MySQL shell (mysql)')
    @click.option('--root', help='Start in root mode', default=False, is_flag=True)
    @click.pass_context
    def shell(ctx: Any, root: bool) -> None:
        with mysql_shell_connect_args(ctx, root or defaultRoot) as args:
            sh.mysql(*args, _fg=True)

    @mysqlGroup.command(help='Start a MySQL admin shell (mysqlsh)')
    @click.option('--root', help='Start in root mode', default=False, is_flag=True)
    @click.pass_context
    def admin(ctx: Any, root: bool) -> None:
        with mysqlsh_shell_connect_args(ctx, root or defaultRoot) as args:
            sh.mysqlsh(*args, _fg=True)

    if not defaultRoot:

        @mysqlGroup.command()
        @click.pass_context
        def app_create(ctx: Any) -> None:
            """Set up db user and database for the given app. Both will use 'name' as their name. Stores pwd as kubernetes secret in the same namespace"""
            with mysql_connect(ctx, root=True) as db:
                q = partial(mysql_query, db)

                secretName, database, username = mysql_convert_name(ctx)
                password = makePassword()

                if q('SHOW DATABASES;')['Database'].isin([database]).any():  # type: ignore
                    click.echo(f'Database "{database}" already exists', err=True)
                    sys.exit(1)

                if q('SELECT User FROM mysql.user;')['User'].isin([username]).any():  # type: ignore
                    click.echo(f'User "{username}" already exists', err=True)
                    sys.exit(1)

                q(f"""CREATE USER IF NOT EXISTS '{username}'@'%' IDENTIFIED BY '{password}';""")
                click.echo(f'Created mysql user "{username}"')

                q(f"""CREATE DATABASE IF NOT EXISTS {database} CHARACTER SET utf8mb4 COLLATE utf8mb4_bin;""")
                click.echo(f'Created mysql database "{database}"')

                q(
                    f"""GRANT SELECT, INSERT, UPDATE, DELETE, ALTER, CREATE, DROP, INDEX, REFERENCES, LOCK TABLES on {database}.* TO '{username}'@'%';"""
                )
                click.echo('Granted permissions for user to database')

                q("""FLUSH PRIVILEGES;""")

                click.echo('Flushed privileges')

                # Create a kubernetes secret for mysql in the target namespace
                k8s_namespace_create(ctx.obj.k8sNamespace, ctx.obj.k8sContext)

                k8s_secret_create(
                    secretName,
                    ctx.obj.k8sNamespace,
                    ctx.obj.k8sContext,
                    {
                        'username': username,
                        'password': password,
                    },
                )
                click.echo('Added mysql secret to kubernetes')

        @mysqlGroup.command()
        @click.pass_context
        def app_exists(ctx: Any) -> None:
            """Check if app exists"""
            secretName, *_ = mysql_convert_name(ctx)

            exists = k8s_secret_exists(secretName, ctx.obj.k8sNamespace, ctx.obj.k8sContext)

            sys.exit(0 if exists else 1)

        @mysqlGroup.command()
        @click.pass_context
        def app_delete(ctx: Any) -> None:
            """Delete user and database for a given app"""
            click.echo('!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!! WARNING !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!')
            click.echo('This will delete the given app from mysql, including the app database and user')

            if click.prompt('Re-type the app name to continue') != ctx.obj.k8sAppName:
                click.echo('Wrong name entered. Aborting', err=True)
                sys.exit(1)

            with mysql_connect(ctx, root=True) as db:
                q = partial(mysql_query, db)
                secretName, database, username = mysql_convert_name(ctx)

                q(f"""REVOKE ALL PRIVILEGES on {database}.* FROM '{username}'@'%';""")
                click.echo(f'Revoked user privileges from "{username}"')

                q(f"""DROP USER '{username}'@'%';""")
                click.echo(f'Dropped user "{username}"')

                q(f"""DROP DATABASE IF EXISTS {database};""")
                click.echo(f'Dropped database "{database}"')

                q("""FLUSH PRIVILEGES;""")
                click.echo('Flushed privileges')

                # Delete kubernetes secret
                k8s_secret_delete(secretName, ctx.obj.k8sNamespace, ctx.obj.k8sContext)
                click.echo('Deleted mysql secret from kubernetes')

        @mysqlGroup.command()
        @click.argument('filename')
        @click.option(
            '--dryrun',
            help='Dryrun without actually affecting database',
            default=False,
            is_flag=True,
        )
        @click.option(
            '--queue-size',
            help='Number of lines of buffer between IO and database',
            default=128,
            type=int,
        )
        @click.pass_context
        def app_import_backup(ctx: Any, filename: str, dryrun: bool, queue_size: int) -> None:
            """Import database backup"""
            if not dryrun:
                click.echo('!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!! WARNING !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!')
                click.echo('This will overwrite the database for the current app!')

                if click.prompt('Re-type the app name to continue') != ctx.obj.k8sAppName:
                    click.echo('Wrong name entered. Aborting', err=True)
                    sys.exit(1)

            class NullPipe:
                def put(self, s: str) -> None:
                    pass

            # Need root in order to diesable foreign key checks etc. on import. We pass in a way to create a pipe
            # because the k8s port forwarding has a 4 hour timeout
            def create_pipe() -> Any:
                if dryrun:
                    return nullcontext((NullPipe(), None))
                return mysql_pipe(ctx, root=True, quiet=True, queue_size=queue_size)

            _, database, _ = mysql_convert_name(ctx)

            backup_pwd = k8s_secret_read_single(
                'app-secrets', ctx.obj.k8sNamespace, ctx.obj.k8sConfig, 'DB-BACKUP-KEY', 'db-backup-key'
            )

            mysql_backup_import(create_pipe, database, filename, backup_pwd, debug_lookback=queue_size)

    return mysqlGroup


def mysql(root: bool = False) -> Any:
    """
    Injects functions into service Config for managing mysql

    Expects:

    """

    def decorator(cls: Any) -> Any:
        prep_config(cls)

        cls.meta.mysql = True

        cls.meta.commandGroups.append(('mysql', _implement(root)))

        return cls

    return decorator
