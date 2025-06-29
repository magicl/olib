# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~

import os
from typing import Any

import click
import sh
from yaml import dump, load

try:
    from yaml import CDumper as Dumper
    from yaml import CLoader as Loader
except ImportError:
    from yaml import Dumper, Loader  # type: ignore[assignment]


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
        kube_root = os.path.expanduser('~/.kube')

        os.makedirs(f'{kube_root}/configs', exist_ok=True)

        configs = []
        for cluster, node in (('dev', 'node0'), ('pub', 'pnode0')):
            # pylint: disable=too-many-function-args
            conf = sh.ssh('-o', 'BatchMode=yes', node, 'microk8s config')
            token = sh.ssh(
                '-o',
                'BatchMode=yes',
                node,
                f'microk8s kubectl get secrets admin-{cluster}-token -n default -o jsonpath=\'{{.data.token}}\' | base64 --decode',
            )
            # pylint: enable=too-many-function-args

            path = f"{kube_root}/configs/{cluster}.yml"

            if os.path.exists(path):
                os.chmod(path, mode=0o700)

            # Update names in config before writing out so multiple can be merged
            doc = load(conf, Loader=Loader)
            doc['clusters'][0]['name'] = f'{cluster}-cluster'
            doc['contexts'][0]['context']['cluster'] = f'{cluster}-cluster'
            doc['contexts'][0]['context']['user'] = f'admin-{cluster}'
            doc['contexts'][0]['name'] = cluster
            doc['users'][0]['name'] = f'admin-{cluster}'

            # Use token for service account created by 'services/system_serviceaccounts'
            del doc['users'][0]['user']['client-certificate-data']
            del doc['users'][0]['user']['client-key-data']
            doc['users'][0]['user']['token'] = token

            conf = dump(doc, Dumper=Dumper)

            with open(path, 'w', encoding='utf-8') as f:
                f.write(conf)

            os.chmod(path, mode=0o400)
            print(f"extracted config: {cluster}")

            configs.append(path)

        # Write kubeconfig file
        kubeconfig_env = ':'.join(str(p) for p in configs)

        flattened_config = sh.kubectl.config.view(
            '--flatten',
            _env={'KUBECONFIG': kubeconfig_env},
        )

        with open(f'{kube_root}/config', 'w', encoding='utf-8') as f:
            f.write(flattened_config)

        print('wrote flattened config')

        ctx.invoke(switch, cluster='dev')

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
