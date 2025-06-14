# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~

import os
from typing import Any

import click
import sh


def register(config: Any) -> None:
    @click.group()
    def k8s() -> None:
        pass

    @k8s.command(
        name='config',
        help='Read k8s cluster configs and store on current machine to allow accessing clusters',
    )
    @click.pass_context
    def config_(ctx: Any) -> None:
        """Hardcoded for now"""
        configs_root = os.path.expanduser('~/.kube/configs')

        os.makedirs(configs_root, exist_ok=True)

        for cluster, node in (('dev', 'node0'), ('pub', 'pnode0')):
            conf = sh.ssh('-o', 'BatchMode=yes', node, 'microk8s config')  # pylint: disable=too-many-function-args
            path = f"{configs_root}/{cluster}.yml"
            with open(path, 'w', encoding='utf-8') as f:
                f.write(conf)

            os.chmod(path, mode=0o400)
            print(f"configured: {cluster}")

        # Should extend this.. look at infrabase/readme

        # ctx.invoke(switch, cluster='dev')

    @k8s.command(help='Switch k8s context to different k8s cluster')
    @click.argument('cluster', type=str)
    def switch(cluster: str) -> None:
        """Switch k8s config files"""
        # from_file = os.path.expanduser(f"~/.kube/configs/{cluster}.yml")
        # to_file = os.path.expanduser('~/.kube/config')

        # shutil.copyfile(from_file, to_file)

        # os.chmod(to_file, mode=0o600)
        # print(f"switched to: {cluster}")

        sh.kubectl('config', 'use-context', cluster, _fg=True)

    if len(k8s.commands):
        config.meta.commandGroups.append(('k8s', k8s))
