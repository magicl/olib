# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~

import queue
import re
import signal
import sys
import tempfile
import time
from contextlib import contextmanager

import click
import sh

from ....utils.kubernetes import k8s_secret_read
from ....utils.secrets import readFileSecret

# Shares a lot of code with postgres template
# pylint: disable=duplicate-code


def mysql_convert_name(ctx):
    name = ctx.obj.k8sAppName

    if any(name.startswith(prefix) for prefix in ['root', 'localroot', 'mysql']):
        click.echo(f'The following name is reserved: "{name}"')
        sys.exit(1)

    secret_name = 'mysql'  # secret_name excludes 'name' so it can be referenced easily in kubernetes templates  # nosec
    database = name.replace('-', '_')
    username = name

    return secret_name, database, username


def mysql_creds(ctx, root=False, use_db: bool | None = None):
    if use_db is None:
        use_db = not root

    database: str | None = None

    if root:
        user = 'root'
        pwd = readFileSecret('$KNOX/infrabase/secrets/infra/mysql-root.txt')
        if use_db:
            _, database, _ = mysql_convert_name(ctx)
    else:
        # Access as current node. Get pwd from kubernetes secret
        secret_name, database, _ = mysql_convert_name(ctx)
        secret = k8s_secret_read(secret_name, ctx.obj.k8sNamespace, ctx.obj.k8sContext)

        user = secret['username']
        pwd = secret['password']

    return user, pwd, database


@contextmanager
def mysql_shell_connect_args(ctx, root=False, quiet=False, use_db: bool | None = None):
    """Opens port, creates a credentials file, and composes arguments for mysql shell"""
    if use_db is None:
        use_db = not root

    user, pwd, database = mysql_creds(ctx, root, use_db)

    with mysql_port_forward(quiet=quiet) as port:
        # Create a temp file for config to pass username / password
        with tempfile.NamedTemporaryFile(mode='w+t') as tempConfig:
            host = '127.0.0.1'

            # Use unencrypted temp file
            tempConfig.write(f"[client]\nuser={user}\npassword={pwd}\n")
            tempConfig.flush()

            # --defaults-file must be the first argument
            args = [f"--defaults-file={tempConfig.name}", f"-h{host}", f"-P{port}"]

            if use_db:
                args.append(f"-D{database}")

            yield args


@contextmanager
def mysqlsh_shell_connect_args(ctx, root=False, use_db: bool | None = None):
    """
    Opens port, and composes arguments for mysql shell
    """
    if use_db is None:
        use_db = not root

    user, _, database = mysql_creds(ctx, root, use_db)

    with mysql_port_forward() as port:
        host = '127.0.0.1'

        args = [f"--user={user}", f"--host={host}", f"--port={port}"]

        if use_db:
            args.append(f"-D{database}")

        yield args


@contextmanager
def mysql_port_forward(quiet=False):
    port = None

    def func(s):
        nonlocal port
        # print(s)
        if m := re.match(r'Forwarding from 127.0.0.1:(\d+) ->', s):
            port = int(m.group(1))

    # Forwarding a service is not straight forward with kubernetes python lib.. Do it with sh
    fwd = sh.kubectl(
        'port-forward',
        'service/mysql',
        ':3306',
        '-n=mysql',
        _bg=True,
        _out=func,
        _err=func,
    )

    while port is None:
        time.sleep(0.1)

    if not quiet:
        print(f"MySQL forwarded to local port {port}")

    try:
        yield port
    finally:
        fwd.signal(signal.SIGHUP)  # Gentle kill


@contextmanager
def mysql_connect(ctx, root=False, use_db: bool | None = None):
    from MySQLdb import _mysql
    from MySQLdb.constants import FIELD_TYPE

    if use_db is None:
        use_db = not root

    user, pwd, database = mysql_creds(ctx, root, use_db)

    with mysql_port_forward() as port:
        # Connect with mysql client. Add more mappings if we need access to more fields
        args = {
            'host': '127.0.0.1',
            'port': port,
            'user': user,
            'password': pwd,
        }
        if use_db:
            args['database'] = database

        yield _mysql.connect(  # pylint: disable=c-extension-no-member
            **args,
            conv={
                FIELD_TYPE.TINY: int,
                FIELD_TYPE.SHORT: int,
                FIELD_TYPE.LONG: int,
                FIELD_TYPE.FLOAT: float,
                FIELD_TYPE.DOUBLE: float,
                FIELD_TYPE.VARCHAR: lambda v: v.decode('utf-8'),
                FIELD_TYPE.VAR_STRING: lambda v: v.decode('utf-8'),
                FIELD_TYPE.STRING: lambda v: v.decode('utf-8'),
            },
        )


@contextmanager
def mysql_pipe(ctx, root=False, quiet=False, queue_size=1024):
    """Open a pipe into mysql. Useful for e.g. restoring backups"""
    with mysql_shell_connect_args(ctx, root, quiet=quiet) as args:
        mysqlIn: queue.Queue = queue.Queue(maxsize=queue_size)
        mysql_ref = sh.mysql(*args, _in=mysqlIn, _bg=True, _no_out=True)

        yield mysqlIn, mysql_ref

        # Add 'quit' command as last entry in queue, and wait for mysql to exit
        mysqlIn.put('quit\n')

        # while not mysqlIn.empty():
        #    time.sleep(0.1)
        mysql_ref.wait()
        if not quiet:
            print('MySQL statements complete')


def mysql_escape(s: str):
    """Note, even though escaped, this is not fully safe, and should only be used by superusers on good input"""
    from MySQLdb._mysql import escape_string

    return escape_string(s.encode('utf-8')).decode('utf-8')


# def mysqlExec(db, q, params, table=True):
#     db.execute(q, params)
#     return _mysql_result(db, table)


def mysql_query(db, q, table=True):
    """Prefer mysqlExec over mysql_query, as mysqlExec handles query parameters in a safer way"""
    db.query(q)
    return _mysql_result(db, table)


def _mysql_result(db, table=True):
    import pandas as pd

    r = db.store_result()
    if r is None:
        return None

    data = r.fetch_row(how=1 if table else 0, maxrows=0)
    if table:
        return pd.DataFrame(data)

    return data
