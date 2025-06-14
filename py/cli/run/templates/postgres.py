# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~

# Shares a lot of code with mysql template
# pylint: disable=duplicate-code

import sys
from collections.abc import Callable
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
from ..utils.mysql_backup import mysql_backup_import
from ..utils.postgres import (
    postgres_connect,
    postgres_convert_name,
    postgres_pipe,
    postgres_query,
    postgres_shell_connect_args,
)
from .base import prep_config


def _implement(defaultRoot: bool = True) -> Any:
    @click.group(help='Postgres commands')
    def postgresGroup() -> None:
        pass

    @postgresGroup.command(help='Start a Postgres shell (postgres)')
    @click.option('--root', help='Start in root mode', default=False, is_flag=True)
    @click.pass_context
    def shell(ctx: Any, root: Any) -> None:
        with postgres_shell_connect_args(ctx, root=root or defaultRoot) as (args, env):
            env = {
                **env,
                'TERM': 'xterm-256color',  # Help psql understand terminal type since we are running through sh
            }
            sh.psql(*args, _fg=True, _env=env)

    @postgresGroup.command(help='Execute one or more postgres queries')
    @click.argument('queries', nargs=-1)
    @click.option('--root', help='Run as root', default=False, is_flag=True)
    @click.option('--no-db', help='Run without selecting a db', default=False, is_flag=True)
    @click.pass_context
    def exec(ctx: Any, queries: Any, root: Any, no_db: Any) -> None:
        with postgres_connect(ctx, root=root, use_db=not no_db) as db:
            q = partial(postgres_query, db)
            # queries = click.get_text_stream('stdin').read().strip().split(';')
            for query in queries:
                if query.strip():
                    click.echo('> ' + query)
                    res = q(query)
                    if res is not None:
                        click.echo(' => ' + str(res))

    if not defaultRoot:

        @postgresGroup.command()
        @click.pass_context
        def app_create(ctx: Any) -> None:
            """Set up db user and database for the given app. Both will use 'name' as their name. Stores pwd as kubernetes secret in the same namespace"""
            with postgres_connect(ctx, root=True) as db:
                q = partial(postgres_query, db)

                secretName, database, username = postgres_convert_name(ctx)
                password = makePassword()

                if q(r'SELECT datname FROM pg_database WHERE datistemplate = false;')['datname'].isin([database]).any():
                    click.echo(f'Database "{database}" already exists', err=True)
                    sys.exit(1)

                if q('SELECT usename FROM pg_user;')['usename'].isin([username]).any():
                    click.echo(f'User "{username}" already exists', err=True)
                    sys.exit(1)

                q(f"""CREATE USER {username} WITH ENCRYPTED PASSWORD '{password}';""")
                click.echo(f'Created postgres user "{username}"')

                q(f"""CREATE DATABASE {database} WITH ENCODING 'utf8';""")
                click.echo(f'Created postgres database "{database}"')

                q(f"""GRANT CONNECT, TEMP ON DATABASE {database} TO {username};""")

            # Must change context to database to set up permissions within db
            with postgres_connect(ctx, root=True, use_db=True) as db:
                q = partial(postgres_query, db)

                q(f"""GRANT USAGE, CREATE ON SCHEMA public TO {username};""")
                q(f"""GRANT SELECT, INSERT, UPDATE, DELETE, REFERENCES ON ALL TABLES IN SCHEMA public TO {username};""")
                q(f"""GRANT USAGE, SELECT, UPDATE ON ALL TABLES IN SCHEMA public TO {username};""")

                click.echo('Granted permissions for user to database')

                for ext in ctx.obj.meta.postgres_extensions:
                    q(f"""CREATE EXTENSION IF NOT EXISTS {ext};""")

                # Create a kubernetes secret for postgres in the target namespace
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
                click.echo('Added postgres secret to kubernetes')

        @postgresGroup.command()
        @click.pass_context
        def app_exists(ctx: Any) -> None:
            """Check if app exists"""
            secretName, *_ = postgres_convert_name(ctx)

            exists = k8s_secret_exists(secretName, ctx.obj.k8sNamespace, ctx.obj.k8sContext)

            sys.exit(0 if exists else 1)

        @postgresGroup.command()
        @click.pass_context
        def app_delete(ctx: Any) -> None:
            """Delete user and database for a given app"""
            click.echo('!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!! WARNING !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!')
            click.echo('This will delete the given app from postgres, including the app database and user')

            if input('Re-type the app name to continue: ') != ctx.obj.k8sAppName:
                click.echo('Wrong name entered. Aborting', err=True)
                sys.exit(1)

            with postgres_connect(ctx, root=True) as db:
                q = partial(postgres_query, db)
                secretName, database, username = postgres_convert_name(ctx)

                q(f"""DROP DATABASE IF EXISTS {database};""")
                click.echo(f'Dropped database "{database}"')

                q(f"""DROP USER IF EXISTS {username};""")
                click.echo(f'Dropped user "{username}"')

                # Delete kubernetes secret
                k8s_secret_delete(secretName, ctx.obj.k8sNamespace, ctx.obj.k8sContext)
                click.echo('Deleted postgres secret from kubernetes')

        @postgresGroup.command()
        @click.pass_context
        def app_clear_db(ctx: Any) -> None:
            """Clear database for a given app"""
            click.echo('!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!! WARNING !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!')
            click.echo('This will delete all data in the database for the given app')

            if input('Re-type the app name to continue: ') != ctx.obj.k8sAppName:
                click.echo('Wrong name entered. Aborting', err=True)
                sys.exit(1)

            with postgres_connect(ctx, root=True, use_db=True) as db:
                q = partial(postgres_query, db)
                _, database, username = postgres_convert_name(ctx)

                q("""DROP SCHEMA IF EXISTS public CASCADE;""")
                q("""CREATE SCHEMA public;""")
                q(f"""GRANT USAGE, CREATE ON SCHEMA public TO {username};""")
                q(f"""GRANT SELECT, INSERT, UPDATE, DELETE, REFERENCES ON ALL TABLES IN SCHEMA public TO {username};""")
                q(f"""GRANT USAGE, SELECT, UPDATE ON ALL TABLES IN SCHEMA public TO {username};""")

                click.echo(f'Cleared database "{database}"')

        @postgresGroup.command()
        @click.argument('filename')
        @click.option(
            '--dryrun',
            help='Dryrun without actually affecting database',
            default=False,
            is_flag=True,
        )
        @click.option(
            '--queue-size',
            help='Dryrun without actually affecting database',
            default=1024,
            type=int,
        )
        @click.pass_context
        def app_import_backup(ctx: Any, filename: Any, dryrun: Any, queue_size: Any) -> None:
            """Import database backup"""
            if not dryrun:
                click.echo('!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!! WARNING !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!')
                click.echo('This will overwrite the database for the current app!')

                if input('Re-type the app name to continue: ') != ctx.obj.k8sAppName:
                    click.echo('Wrong name entered. Aborting', err=True)
                    sys.exit(1)

            class NullPipe:
                def put(self, s: Any) -> None:
                    pass

            # Need root in order to diesable foreign key checks etc. on import. We pass in a way to create a pipe
            # because the k8s port forwarding has a 4 hour timeout
            def create_pipe() -> Any:
                if dryrun:
                    return nullcontext((NullPipe(), None))
                return postgres_pipe(ctx, root=True, quiet=True, queue_size=queue_size)

            _, database, _ = postgres_convert_name(ctx)

            backup_pwd = k8s_secret_read_single(
                'app-secrets', ctx.obj.k8sNamespace, ctx.obj.k8sContext, 'DB-BACKUP-KEY', 'db-backup-key'
            )

            mysql_backup_import(create_pipe, database, filename, backup_pwd)

    return postgresGroup


def postgres(root: bool = False, extensions: list[str] | None = None) -> Callable[[Any], Any]:
    """
    Injects functions into service Config for managing postgres

    Expects:

    """

    def decorator(cls: Any) -> Any:
        prep_config(cls)

        cls.meta.postgres = True
        cls.meta.postgres_extensions = extensions or []

        cls.meta.commandGroups.append(('postgres', _implement(root)))

        return cls

    return decorator
