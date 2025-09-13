# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~
import os
import tempfile
from collections.abc import Generator
from contextlib import contextmanager

import sh


@contextmanager
def ssh_session(
    host: str,
    user: str | None = None,
    *,
    port: int | None = None,
    control_path: str | None = None,
    control_persist: str = '10m',
    forward_agent: bool = False,
    strict_host_key_checking: str | None = None,  # e.g. 'no'
    close_on_exit: bool = True,
) -> Generator[tuple[sh.Command, sh.Command], None, None]:
    """
    Context manager that sets up an SSH master connection
    and yields baked ssh/scp commands.

    Example:
        with ssh_session('server.example.com', user='alice') as (ssh, scp):
            print(ssh('hostname'))
            scp('file.txt', 'alice@server.example.com:/tmp/file.txt')
    """

    dest = f'{user}@{host}' if user and '@' not in host else host
    socket = control_path or os.path.join(tempfile.gettempdir(), f'ssh-{host}.sock')

    def base_ctl_args() -> list[str]:
        args = ['-o', f'ControlPath={socket}', '-o', 'ControlMaster=auto', '-o', f'ControlPersist={control_persist}']
        if port:
            args.extend(['-p', str(port)])
        if forward_agent:
            args.append('-A')
        if strict_host_key_checking is not None:
            args.extend(['-o', f'StrictHostKeyChecking={strict_host_key_checking}'])
        return args

    def start_master() -> None:
        sh.ssh('-M', '-N', '-f', *base_ctl_args(), dest)

    def stop_master() -> None:
        # pylint: disable=unexpected-keyword-arg
        sh.ssh('-O', 'exit', *base_ctl_args(), dest, _ok_code=[0, 255])
        # pylint: enable=unexpected-keyword-arg

    # Start master
    start_master()

    try:
        ssh_baked = sh.ssh.bake(*base_ctl_args(), dest)
        scp_baked = sh.scp.bake(*base_ctl_args())
        yield ssh_baked, scp_baked
    finally:
        if close_on_exit:
            stop_master()
