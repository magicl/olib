# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~

import queue
import re
import signal
import sys
import time
from contextlib import contextmanager
from typing import Generator
import click
import sh
import psycopg
from ....utils.kubernetes import k8s_secret_read
from ....utils.secrets import readFileSecret

# Shares a lot of code with mysql template
# pylint: disable=duplicate-code


def postgres_convert_name(ctx: click.Context) -> tuple[str, str, str]:
    name = ctx.obj.k8sAppName

    if any(name.startswith(prefix) for prefix in ['root', 'localroot', 'postgres']):
        click.echo(f'The following name is reserved: "{name}"')
        sys.exit(1)

    secret_name = (
        'postgres'  # secret_name excludes 'name' so it can be referenced easily in kubernetes templates # nosec
    )
    database = name.replace('-', '_')
    username = name.replace('-', '_')

    return secret_name, database, username


def postgres_creds(ctx: click.Context, root: bool = False, use_db: bool | None = None) -> tuple[str, str, str | None]:
    if use_db is None:
        use_db = not root

    database: str | None = None

    if root:
        user = 'postgres'
        pwd = readFileSecret('$KNOX/infrabase/secrets/infra/postgres-root.txt')

        if use_db:
            _, database, _ = postgres_convert_name(ctx)
    else:
        # Access as current node. Get pwd from kubernetes secret
        secret_name, database, _ = postgres_convert_name(ctx)
        secret = k8s_secret_read(secret_name, ctx.obj.k8sNamespace, ctx.obj.k8sContext)

        user = secret['username']
        pwd = secret['password']

    return user, pwd, database


@contextmanager
def postgres_shell_connect_args(ctx: click.Context, root: bool = False, quiet: bool = False, use_db: bool | None = None) -> Generator[tuple[list[str], dict[str, str]], None, None]:
    """Opens port, creates a credentials file, and composes arguments for postgres shell"""
    if use_db is None:
        use_db = not root

    user, pwd, database = postgres_creds(ctx, root, use_db)

    with postgres_port_forward(quiet=quiet) as port:
        host = '127.0.0.1'

        args = [
            f"--host={host}",
            f"--port={port}",
            f"--username={user}",
            '--no-password',
        ]
        env = {'PGPASSWORD': pwd}

        if use_db:
            args.append(f"--dbname={database}")

        yield args, env


@contextmanager
def postgres_port_forward(quiet=False):
    port = None

    def func(s):
        nonlocal port
        # print(s)
        if m := re.match(r'Forwarding from 127.0.0.1:(\d+) ->', s):
            port = int(m.group(1))

    # Forwarding a service is not straight forward with kubernetes python lib.. Do it with sh
    fwd = sh.kubectl(
        'port-forward',
        'service/postgres',
        ':5432',
        '-n=postgres',
        _bg=True,
        _out=func,
        _err=func,
    )

    while port is None:
        time.sleep(0.1)

    if not quiet:
        print(f"Postgres forwarded to local port {port}")

    try:
        yield port
    finally:
        fwd.signal(signal.SIGHUP)  # Gentle kill


@contextmanager
def postgres_connect(ctx: click.Context, root: bool = False, use_db: bool | None = None) -> Generator[psycopg.Cursor, None, None]:
    import psycopg

    if use_db is None:
        use_db = not root

    user, pwd, database = postgres_creds(ctx, root, use_db)

    with postgres_port_forward() as port:
        # Connect with postgres client. Add more mappings if we need access to more fields
        host = '127.0.0.1'
        url = f"postgresql://{user}:{pwd}@{host}:{port}"

        if use_db:
            url += f"/{database}"

        with psycopg.connect(url) as connection:  # pylint: disable=not-context-manager
            connection.autocommit = True

            with connection.cursor() as cursor:
                yield cursor
                # cursor.commit()


@contextmanager
def postgres_pipe(ctx: click.Context, root: bool = False, quiet: bool = False, queue_size: int = 1024) -> Generator[tuple[queue.Queue, sh.Command], None, None]:
    """Open a pipe into postgres. Useful for e.g. restoring backups"""
    with postgres_shell_connect_args(ctx, root, quiet=quiet) as args:
        postgresIn: queue.Queue = queue.Queue(maxsize=queue_size)
        postgres_ref = sh.postgres(*args, _in=postgresIn, _bg=True, _no_out=True)

        yield postgresIn, postgres_ref

        # Add 'quit' command as last entry in queue, and wait for postgres to exit
        postgresIn.put('quit\n')

        # while not postgresIn.empty():
        #    time.sleep(0.1)
        postgres_ref.wait()
        if not quiet:
            print('Postgres statements complete')


def postgres_query(db, q, values=(), table=True):
    """Use e.g. %s as placeholders for values, and pass values in 'values' as a tuple"""
    db.execute(q, values)

    if q.startswith('SELECT'):
        return _postgres_result(db, table)

    return None


def _postgres_result(db, table=True):
    import pandas as pd

    if db.rowcount == -1:
        # -1 is returned when the query does not have any return values
        return None

    data = db.fetchall()
    if data is None:
        return None

    if table:
        # Add in column data
        columns = [col.name for col in db.description]
        return pd.DataFrame(data, columns=columns)

    return data
