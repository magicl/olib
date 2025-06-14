# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~

import re
import sys
import time
from contextlib import contextmanager
from typing import Any
from collections.abc import Generator

import click
import sh

from ....utils.secrets import readFileSecret


def redis_convert_name(ctx: Any) -> tuple[str, int]:
    name = ctx.obj.k8sAppName

    if any(name.startswith(prefix) for prefix in ['root', 'localroot', 'redis']):
        click.echo(f'The following name is reserved: "{name}"')
        sys.exit(1)

    secret_name = 'redis'  # secret_name excludes 'name' so it can be referenced easily in kubernetes templates  # nosec
    database = 0

    return secret_name, database


def redis_creds(ctx: Any, root: bool | None = None) -> tuple[str, int | None]:
    # Always using root secret for redis
    pwd = readFileSecret('$KNOX/infrabase/secrets/infra/redis-root.txt')

    if root:
        database = None
    else:
        database = 0

    return pwd, database


@contextmanager
def redis_port_forward() -> Generator[int, None, None]:
    port = None

    def func(s: str) -> None:
        nonlocal port
        # print(s)
        if m := re.match(r'Forwarding from 127.0.0.1:(\d+) ->', s):
            port = int(m.group(1))

    # Forwarding a service is not straight forward with kubernetes python lib.. Do it with sh
    fwd = sh.kubectl(
        'port-forward',
        'service/redis',
        ':6379',
        '-n=redis',
        _bg=True,
        _out=func,
        _err=func,
    )

    while port is None:
        time.sleep(0.1)

    print(f"Redis forwarded to local port {port}")

    try:
        yield port
    finally:
        fwd.terminate()


# @contextmanager
# def redisConnect(ctx, root):
#     import redis as _redis

#     pwd, database = redis_creds(ctx, root)

#     with redis_port_forward() as port:
#         # Connect with redis client
#         args = {
#             'host': '127.0.0.1',
#             'port': port,
#         }
#         if database is not None:
#             args['db'] = database

#         yield _redis.Redis(**args)


# def redisQuery(db, q, table=True):
#     raise Exception('implement')
