# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~

# pylint: disable=duplicate-code

import hashlib
import os
from functools import partial
from typing import Any, NamedTuple

import click
import sh

from ....utils.kubernetes import (
    k8s_namespace_create,
    k8s_secret_create,
    k8s_secret_delete,
)
from ....utils.passwords import makePassword
from ..utils.mysql import mysql_connect, mysql_escape, mysql_query
from ..utils.postgres import postgres_connect, postgres_query
from .base import prep_config


class DjangoConfig(NamedTuple):
    settings: str  # django settings module
    working_dir: str = './'
    manage_py: str = './manage.py'
    collectstatic: bool = True
    admin_user_extra_fields: dict[str, Any] = {}
    user_table: str = 'auth_user'

    # def rel_manage_py_path(self) -> str:
    #    return os.path.normpath(os.path.join(self.working_dir, self.manage_py))

    def hash(self) -> str:
        # Create a simple 6 digit hash of the settings_module and working_dir for caching
        return hashlib.sha256(f'{self.settings}{self.working_dir}'.encode()).hexdigest()[:6]

    def __hash__(self) -> str:
        return hash(f'{self.settings}{self.working_dir}')

    def name(self) -> str:
        return self.settings.split('.')[-2]


def app_create_superuser_post(cls: Any, ctx: Any, q: Any, username: str, email: str) -> None:
    pass


def _implement() -> Any:
    @click.group(help='MySQL commands')
    def mysqlGroup() -> None:
        pass

    @mysqlGroup.command()
    @click.pass_context
    def app_create_secret(ctx: Any) -> None:
        """Create secret for the django app with the given name"""
        secretName = 'django'
        secret = makePassword(length=50, symbols=True)

        # Create a kubernetes secret for django in the target namespace
        k8s_namespace_create(ctx.obj.k8sNamespace, ctx.obj.k8sContext)

        k8s_secret_create(
            secretName,
            ctx.obj.k8sNamespace,
            ctx.obj.k8sContext,
            {
                'secret': secret,
            },
        )
        click.echo('Added django secret to kubernetes')

    @mysqlGroup.command()
    @click.pass_context
    def app_delete_secret(ctx: Any) -> None:
        """Create secret for the django app with the given name"""
        secretName = 'django'

        # Delete kubernetes secret
        k8s_secret_delete(secretName, ctx.obj.k8sNamespace, ctx.obj.k8sContext)
        click.echo('Deleted django secret from kubernetes')

    @mysqlGroup.command()
    @click.pass_context
    def app_create_superuser(ctx: Any) -> None:
        """Create superuser for django app"""
        django_config = ctx.obj.meta.django_primary

        fname = mysql_escape(click.prompt('first name'))
        username = mysql_escape(click.prompt('username'))
        email = mysql_escape(click.prompt('email'))
        password = click.prompt('password', hide_input=True)
        password_hash = sh.python3(
            django_config.manage_py, 'hash_password', password, _bg=True, _cwd=django_config.working_dir
        ).strip()

        # Build extra fields columns and values
        extra_fields = django_config.admin_user_extra_fields
        extra_columns = ', '.join(extra_fields.keys()) if extra_fields else ''
        extra_columns_prefix = ', ' + extra_columns if extra_columns else ''

        if ctx.obj.meta.mysql:
            with mysql_connect(ctx, root=False) as db:
                q = partial(mysql_query, db)

                # Build extra field values for MySQL (escape each value)
                if extra_fields:
                    extra_escaped_values = [f"'{mysql_escape(str(value))}'" for value in extra_fields.values()]
                    extra_values = ', ' + ', '.join(extra_escaped_values)
                else:
                    extra_values = ''

                q(
                    f"""INSERT INTO {django_config.user_table} (username, email, password, first_name, last_name{extra_columns_prefix}, is_superuser, is_staff, is_active, date_joined) values ('{username}', '{email}', '{password_hash}', '{fname}', ''{extra_values}, true, true, true, now());""",  # nosec
                )

        elif ctx.obj.meta.postgres:
            with postgres_connect(ctx, use_db=True) as db:
                q = partial(postgres_query, db)

                # Build parameter placeholders and values for PostgreSQL
                extra_placeholders = ', ' + ', '.join(['%s'] * len(extra_fields)) if extra_fields else ''
                extra_values = tuple(extra_fields.values()) if extra_fields else ()

                q(
                    f"""INSERT INTO {django_config.user_table} (username, email, password, first_name, last_name{extra_columns_prefix}, is_superuser, is_staff, is_active, date_joined) values (%s, %s, %s, %s, %s{extra_placeholders}, true, true, true, now());""",  # nosec
                    (username, email, password_hash, fname, '') + extra_values,
                )

        else:
            raise Exception('No database selected')

        ctx.obj.config.app_create_superuser_post(ctx, q, username, email)

    @mysqlGroup.command(context_settings={'ignore_unknown_options': True, 'help_option_names': []})
    @click.argument('args', nargs=-1)
    @click.pass_context
    def manage(ctx: Any, args: tuple[str, ...]) -> None:
        """Run manage.py commands"""
        django_config = ctx.obj.meta.django_primary
        sh.python3(django_config.manage_py, *args, _fg=True, _cwd=django_config.working_dir)

    return mysqlGroup


def django(configs: list[DjangoConfig]) -> Any:
    """
    Injects functions into service Config for managing django

    Expects:

    """

    def decorator(cls: Any) -> Any:
        prep_config(cls)

        cls.meta.django = configs
        cls.meta.django_primary = configs[0]

        cls.meta.commandGroups.append(('django', _implement()))

        # Ensure correct django settings have been configurated
        # os.environ.setdefault('DJANGO_SETTINGS_MODULE', settings)
        # os.environ['PYTHONPATH'] = f'{os.environ.get('PYTHONPATH', '')}:{cls.meta.django_working_dir}'

        for f in (app_create_superuser_post,):
            if not hasattr(cls, f.__name__):
                setattr(cls, f.__name__, classmethod(f))

        return cls

    return decorator
