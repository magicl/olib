# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~

import glob
import os
import shutil
import signal
import sys
from collections.abc import Callable
from typing import Any

import click
import parproc as pp
import sh
from dotenv import dotenv_values

from ....utils.kubernetes import (
    k8s_job_wait_for_completion,
    k8s_namespace_create,
    k8s_secret_create_or_update,
)
from .base import prep_config

HELM_BURST_LIMIT = 5


def images_build_pre(cls: Any, ctx: click.Context, k8s: bool = False) -> None:
    """
    Override in Config to do work before images are built. Either run actions directly, or set up
    parproc tasks with now=True
    """
    click.echo('  None')


def k8s_update_pre(cls: Any, ctx: click.Context, k8s: bool = False) -> None:
    """
    Override in Config to do work before k8s is updated. Either run actions directly, or set up
    parproc tasks with now=True
    """
    click.echo('  None')


def run_images_build_pre(cls: Any, ctx: click.Context, k8s: bool = False) -> None:
    click.echo('Pre-build Steps For Image...')
    cls.images_build_pre(ctx, k8s=k8s)
    pp.wait_clear(exception_on_failure=True)


def run_k8s_update_pre(cls: Any, ctx: click.Context, k8s: bool = False) -> None:
    click.echo('Pre-update Steps For K8s...')
    cls.k8s_update_pre(ctx, k8s=k8s)
    pp.wait_clear(exception_on_failure=True)


def images_build(
    cls: Any,
    ctx: click.Context,
    images: str | None = None,
    debug: bool = False,
    no_pre_build: bool = False,
    force: bool = False,
    k8s: bool = False,
) -> None:
    if not no_pre_build:
        run_images_build_pre(cls, ctx, k8s=k8s)

    click.echo('Building Image...')
    meta = ctx.obj.config.meta
    containers = {**meta.build_containers, **ctx.obj.inst.get('containers', {})}

    accepted_images = images.split(',') if images is not None else None
    for image_name, dockerfile in containers.items():
        if accepted_images is not None and image_name not in accepted_images:
            continue

        options = f"build -t {image_name} -f {dockerfile}"
        if debug:
            options = f"{options} --progress=plain"
        if force:
            options = f"{options} --no-cache"

        sh.bash('-c', f"docker {options} .", _fg=True)


def images_push(cls: Any, ctx: click.Context, images: str | None = None) -> None:
    click.echo('Pushing Image...')
    meta = ctx.obj.config.meta
    inst = ctx.obj.inst
    containers = {**meta.build_containers, **ctx.obj.inst.get('containers', {})}

    accepted_images = images.split(',') if images is not None else None
    for image_name, _ in containers.items():
        if accepted_images is not None and image_name not in accepted_images:
            continue

        sh.bash(
            '-c',
            f'''
            docker image tag {image_name}:latest {inst['pck_registry']}/{meta.build_category}/{meta.build_name}/{image_name}:latest
            docker --tlscacert $KNOX/infrabase/root-ca.pem image push {inst['pck_registry']}/{meta.build_category}/{meta.build_name}/{image_name}:latest
            ''',
            _fg=True,
        )


def images_analyze(cls: Any, ctx: click.Context, images: str | None = None) -> None:
    """Runs Dive (https://github.com/wagoodman/dive)"""
    if shutil.which('dive') is None:
        click.echo('Installing dive...')
        try:
            with sh.contrib.sudo:
                sh.snap('install', 'dive', _fg=True)
                sh.snap(
                    'connect',
                    'dive:docker-executables',
                    'docker:docker-executables',
                    _fg=True,
                )
                sh.snap('connect', 'dive:docker-daemon', 'docker:docker-daemon', _fg=True)
        except sh.ErrorReturnCode as e:
            click.echo(f"Dive installation failed: {e}", err=True)
            sys.exit(1)

    click.echo('Running dive...')
    meta = ctx.obj.config.meta
    inst = ctx.obj.inst
    containers = {**meta.build_containers, **ctx.obj.inst.get('containers', {})}

    accepted_images = images.split(',') if images is not None else None
    for image_name, _ in containers.items():
        if accepted_images is not None and image_name not in accepted_images:
            continue

        sh.dive(
            f'docker://{inst['pck_registry']}/{meta.build_category}/{meta.build_name}/{image_name}:latest', _fg=True
        )


def k8s_push_config(cls: Any, ctx: click.Context) -> None:
    click.echo('Pushing Config to Kubernetes...')
    inst = ctx.obj.inst

    # Create env configmap
    if inst['env_configmaps']:
        # Ensure namespace exists
        k8s_namespace_create(ctx.obj.k8sNamespace, ctx.obj.k8sContext)

        for configmap_name, configmap_file in inst['env_configmaps'].items():
            config = sh.kubectl(
                'create',
                'configmap',
                configmap_name,
                f'--from-env-file={configmap_file}',
                '--dry-run=client',
                '-o',
                'yaml',
                '-n',
                ctx.obj.k8sNamespace,
                f'--context={ctx.obj.k8sContext}',
            )

            sh.kubectl(
                'apply',
                '-f',
                '-',
                '-n',
                ctx.obj.k8sNamespace,
                f'--context={ctx.obj.k8sContext}',
                _in=config,
                _out=sys.stdout,
                _err=sys.stderr,
            )


def k8s_push_secrets(cls: Any, ctx: click.Context) -> None:
    """
    Rules:
        Prefix a filename with _ and it will be excluded
        Use file:{filename} as a value in a secret file to load the contents of that file

    """
    click.echo('Pushing Secrets to Kubernetes...')
    inst = ctx.obj.inst

    for secret_file_glob_ in inst.get('secret_files', []):
        secret_file_glob = os.path.expandvars(secret_file_glob_)

        secret_files = glob.glob(secret_file_glob)
        for secret_file in secret_files:
            if os.path.basename(secret_file).startswith('_'):
                # Exclude file.. This is included in other files
                continue

            # Secret files have a config-file format, with key=value pairs
            env_vars = dotenv_values(secret_file)

            # Store k8s secrets with the name of the secret file
            secret_name = os.path.basename(secret_file)

            # Filter out None values and if a value starts with file:, load that file from the same directory
            final_env_vars = {}
            for k, v in env_vars.items():
                if v is None:
                    continue
                if v.startswith('file:'):
                    with open(os.path.join(os.path.dirname(secret_file), v[5:]), encoding='utf-8') as f:
                        value = f.read()
                else:
                    value = v
                final_env_vars[k] = value

            k8s_secret_create_or_update(secret_name, ctx.obj.k8sNamespace, ctx.obj.k8sContext, final_env_vars)


def k8s_migrate(cls: Any, ctx: click.Context, break_on_error: bool = False) -> None:
    click.echo('Applying Migrations...')
    meta = ctx.obj.meta

    # Ensure namespace exists
    k8s_namespace_create(ctx.obj.k8sNamespace, ctx.obj.k8sContext)

    if meta.build_helm_migrate is None:
        sh.kubectl(
            'apply', '-f', 'migration.yml', '-n', ctx.obj.k8sNamespace, f'--context={ctx.obj.k8sContext}', _fg=True
        )
    else:
        helm_values = [arg for v in ctx.obj.inst['helm_values'] for arg in ('-f', v)]
        sh.helm(
            'upgrade',
            '--install',
            'migration',
            meta.build_helm_migrate,
            '-n',
            ctx.obj.k8sNamespace,
            f'--kube-context={ctx.obj.k8sContext}',
            '--create-namespace',
            f'--burst-limit={HELM_BURST_LIMIT}',
            *helm_values,
            _fg=True,
        )

    success = True
    if not k8s_job_wait_for_completion('migration', ctx.obj.k8sNamespace, ctx.obj.k8sContext):
        if break_on_error:
            print('Hit C, Enter to continue')
            breakpoint()  # pylint: disable=forgotten-debug-statement

        success = False

    if meta.build_helm_migrate is None:
        sh.kubectl(
            'delete', '-f', 'migration.yml', '-n', ctx.obj.k8sNamespace, f'--context={ctx.obj.k8sContext}', _fg=True
        )
    else:
        sh.helm(
            'uninstall',
            'migration',
            '-n',
            ctx.obj.k8sNamespace,
            f'--kube-context={ctx.obj.k8sContext}',
            f'--burst-limit={HELM_BURST_LIMIT}',
            _fg=True,
        )

    if not success:
        click.echo('Migrations failed', err=True)
        sys.exit(1)


def k8s_deploy(cls: Any, ctx: click.Context, deployments: str | None) -> None:
    click.echo('Deploying to Kubernetes...')
    meta = ctx.obj.meta
    # inst = ctx.obj.inst
    accepted_deployments = deployments.split(',') if deployments is not None else None

    # Ensure namespace exists
    k8s_namespace_create(ctx.obj.k8sNamespace, ctx.obj.k8sContext)

    # Do we already have deployed services from app
    need_deploy = bool(sh.kubectl('get', 'service', '-n', ctx.obj.k8sNamespace, f'--context={ctx.obj.k8sContext}'))

    if meta.build_helm_deploy is None:
        # Expect a 'deploy.yml' file with the full deployment
        sh.kubectl(
            'apply', '-f', 'deployment.yml', '-n', ctx.obj.k8sNamespace, f'--context={ctx.obj.k8sContext}', _fg=True
        )

    else:
        # Build based on helm chart
        helm_values = [arg for v in ctx.obj.inst['helm_values'] for arg in ('-f', v)]
        sh.helm(
            'upgrade',
            '--install',
            meta.build_name,
            meta.build_helm_deploy,
            '-n',
            ctx.obj.k8sNamespace,
            f'--kube-context={ctx.obj.k8sContext}',
            '--create-namespace',
            f'--burst-limit={HELM_BURST_LIMIT}',
            *helm_values,
            _fg=True,
        )

    if need_deploy:
        for d in meta.build_deployments:
            if accepted_deployments is not None and d not in accepted_deployments:
                continue

            sh.kubectl(
                'rollout',
                'restart',
                f'deployment/{d}',
                '-n',
                ctx.obj.k8sNamespace,
                f'--context={ctx.obj.k8sContext}',
                _fg=True,
            )


def k8s_uninstall(cls: Any, ctx: click.Context) -> None:
    click.echo('Deleting from Kubernetes...')
    meta = ctx.obj.meta

    if meta.build_helm_deploy is None:
        sh.kubectl(
            'delete', '-f', 'deployment.yml', '-n', ctx.obj.k8sNamespace, f'--context={ctx.obj.k8sContext}', _fg=True
        )

    else:
        sh.helm(
            'uninstall',
            meta.build_name,
            '-n',
            ctx.obj.k8sNamespace,
            f'--kube-context={ctx.obj.k8sContext}',
            f'--burst-limit={HELM_BURST_LIMIT}',
            _fg=True,
        )


def docker_run(cls: Any, ctx: click.Context) -> None:
    click.echo('Running image on Docker...')
    meta = ctx.obj.meta
    sh.bash(
        '-c',
        f"""
    echo "Mounted on http://127.0.0.1:{meta.build_localMountPort}\n---"
    docker run -p {meta.build_localMountPort}:{meta.build_servicePort} {meta.build_name}
    """,
        _fg=True,
    )


def docker_compose(
    cls: Any, ctx: click.Context, no_build: bool = False, debug: bool = False, force: bool = False
) -> None:
    click.echo('Running Docker Compose...')
    meta = ctx.obj.meta

    if meta.build_compose is None:
        raise Exception('buildSingleService.compose not defined')

    # echo "Mounted on http://127.0.0.1:{meta.build_localMountPort}\n---"

    env = {
        'UID': str(os.getuid()),
        'GID': str(os.getgid()),
        'COMPOSE_BAKE': 'true',  # Use new, faster compose engine
        **os.environ,
    }

    # Temporarily mask SIGINT from python. We only want docker compose to handle it
    original_sigint = signal.signal(signal.SIGINT, signal.SIG_IGN)
    try:
        build_str = '' if no_build else '--build'

        options = ''
        if debug:
            options = f"{options} --progress=plain"
        if force:
            build_str = f"{build_str} --force-recreate"

        sh.bash(
            '-c',
            f"""
        docker compose -f {meta.build_compose} {options} up {build_str} --abort-on-container-exit --remove-orphans;
        docker compose -f {meta.build_compose} down
        """,
            _fg=True,
            _env=env,
        )
    except sh.ErrorReturnCode:
        # Error most likely due to SIGINT. Ignore it
        pass
    finally:
        # Restore original SIGINT handler
        signal.signal(signal.SIGINT, original_sigint)


def docker_shell(cls: Any, ctx: click.Context) -> None:
    click.echo('Running image on Docker with /bin/bash shell...')
    meta = ctx.obj.meta
    sh.bash(
        '-c',
        f"""
    echo "Mounted on http://127.0.0.1:{meta.build_localMountPort}\n---"
    docker run -p {meta.build_localMountPort}:{meta.build_servicePort} --entrypoint /bin/bash -it {meta.build_name}
    """,
        _fg=True,
    )


def _implementImage() -> Any:
    @click.group(chain=True)
    @click.pass_context
    def imageGroup(ctx: click.Context) -> None:
        pass

    @imageGroup.command()
    @click.option('--images', help='Comma separated list of image names. All if empty', type=str)
    @click.option('--debug', help='Output all build info', default=False, is_flag=True)
    @click.option('--no-pre-build', help='Skip pre-build step', default=False, is_flag=True)
    @click.option('--force', help='Force build.  Ignore cache', default=False, is_flag=True)
    @click.pass_context
    def build(ctx: click.Context, images: str | None, debug: bool, no_pre_build: bool, force: bool) -> None:
        """Build container"""
        ctx.obj.config.images_build(ctx, images=images, debug=debug, no_pre_build=no_pre_build, force=force, k8s=True)

    @imageGroup.command()
    @click.option('--images', help='Comma separated list of image names. All if empty', type=str)
    @click.option('--debug', help='Output all build info', default=False, is_flag=True)
    @click.option('--no-pre-build', help='Skip pre-build step', default=False, is_flag=True)
    @click.pass_context
    def push(ctx: click.Context, images: str | None, debug: bool, no_pre_build: bool) -> None:
        """Push container to registry"""
        ctx.obj.config.images_build(ctx, images=images, debug=debug, no_pre_build=no_pre_build, k8s=True)
        ctx.obj.config.images_push(ctx, images=images)

    @imageGroup.command()
    @click.option('--images', help='Comma separated list of image names. All if empty', type=str)
    @click.pass_context
    def analyze(ctx: click.Context, images: str | None) -> None:
        """Analyze image"""
        ctx.obj.config.images_analyze(ctx, images=images)

    return imageGroup


def _implementApp() -> Any:
    @click.group(chain=True)
    @click.pass_context
    def appGroup(ctx: click.Context) -> None:
        pass

    @appGroup.command()
    @click.pass_context
    def pre_build(ctx: click.Context) -> None:
        """Pre-build step"""
        run_images_build_pre(ctx.obj.config, ctx, k8s=True)

    @appGroup.command()
    @click.pass_context
    def push_secrets(ctx: click.Context) -> None:
        """Push secrets to Kubernetes"""
        ctx.obj.config.k8s_push_secrets(ctx)

    @appGroup.command()
    @click.pass_context
    def push_config(ctx: click.Context) -> None:
        """Push config to Kubernetes"""
        ctx.obj.config.k8s_push_config(ctx)

    @appGroup.command()
    @click.option('--images', help='Comma separated list of image names. All if empty', type=str)
    @click.option(
        '--deployments',
        help='Comma separated list of deployments. All if empty',
        type=str,
    )
    @click.option('--no-migrate', help='Skip migrations', default=False, is_flag=True)
    @click.option('--no-build', help='Skip build step', default=False, is_flag=True)
    @click.option('--no-pre-build', help='Skip pre-build step', default=False, is_flag=True)
    @click.pass_context
    def deploy(
        ctx: click.Context,
        images: str | None,
        deployments: str | None,
        no_migrate: bool,
        no_build: bool,
        no_pre_build: bool,
    ) -> None:
        """Deploy container"""
        if not no_build:
            ctx.obj.config.images_build(ctx, images=images, no_pre_build=no_pre_build, k8s=True)
            ctx.obj.config.images_push(ctx, images=images)

        ctx.obj.config.k8s_push_secrets(ctx)
        ctx.obj.config.k8s_push_config(ctx)
        if ctx.obj.meta.django and not no_migrate:
            ctx.obj.config.k8s_migrate(ctx)
        ctx.obj.config.k8s_deploy(ctx, deployments=deployments)

    @appGroup.command()
    @click.option('--break-on-error', default=False, is_flag=True)
    @click.pass_context
    def migrate(ctx: click.Context, break_on_error: bool) -> None:
        """Deploy container"""
        ctx.obj.config.k8s_push_config(ctx)
        if ctx.obj.meta.django:
            ctx.obj.config.k8s_migrate(ctx, break_on_error)

    @appGroup.command()
    @click.pass_context
    def uninstall(ctx: click.Context) -> None:
        """Uninstall container"""
        ctx.obj.config.k8s_uninstall(ctx)

    return appGroup


def _implementDocker() -> Any:
    @click.group(chain=True)
    @click.pass_context
    def dockerGroup(ctx: click.Context) -> None:
        pass

    @dockerGroup.command('run')
    @click.option('--no-build', help='Skip build step', default=False, is_flag=True)
    @click.option('--no-pre-build', help='Skip pre-build step', default=False, is_flag=True)
    @click.pass_context
    def run(ctx: click.Context, no_build: bool, no_pre_build: bool) -> None:
        """Run container in docker"""
        if not no_build:
            ctx.obj.config.images_build(ctx, no_pre_build=no_pre_build)
        ctx.obj.config.docker_run(ctx)

    @dockerGroup.command('compose')
    @click.option('--no-build', help='Skip build step', default=False, is_flag=True)
    @click.option('--no-pre-build', help='Skip pre-build step', default=False, is_flag=True)
    @click.option('--debug', help='Output all build info', default=False, is_flag=True)
    @click.option('--force', help='Force build.  Ignore cache', default=False, is_flag=True)
    @click.pass_context
    def compose(ctx: click.Context, no_build: bool, no_pre_build: bool, debug: bool, force: bool) -> None:
        """Run container in docker"""
        if not no_pre_build:
            run_images_build_pre(ctx.obj.config, ctx, k8s=False)
        ctx.obj.config.docker_compose(ctx, no_build=no_build, debug=debug, force=force)

    @dockerGroup.command('shell')
    @click.pass_context
    def shell(ctx: click.Context) -> None:
        """Run container in docker with shell"""
        ctx.obj.config.docker_shell(ctx)

    return dockerGroup


def buildSingleService(
    name: str,
    category: str,
    servicePort: int,
    localMountPort: int,
    deployments: list[str] | None = None,
    containers: dict[str, str] | None = None,
    helm_deploy: str | None = None,
    helm_migrate: str | None = None,
    compose: str | None = None,
) -> Callable[[Any], Any]:
    """
    Injects functions into service Config for building, deploying etc.

    Expects:
    - deployment.yml file containing all kubernetes components
    - deployment should be named {name}-deployment
    - tls secret should be named {name}-tls
    """

    def decorator(cls: Any) -> Any:
        prep_config(cls)

        cls.meta.build_name = name
        cls.meta.build_category = category
        cls.meta.build_servicePort = servicePort
        cls.meta.build_localMountPort = localMountPort
        cls.meta.build_deployments = deployments
        cls.meta.build_containers = containers or {name: './Dockerfile'}
        cls.meta.build_helm_deploy = helm_deploy
        cls.meta.build_helm_migrate = helm_migrate
        cls.meta.build_compose = compose
        cls.meta.commandGroups.append(('image', _implementImage()))
        cls.meta.commandGroups.append(('app', _implementApp()))
        cls.meta.commandGroups.append(('docker', _implementDocker()))

        for f in (
            images_build_pre,
            images_build,
            images_push,
            images_analyze,
            k8s_update_pre,
            k8s_push_config,
            k8s_push_secrets,
            k8s_migrate,
            k8s_deploy,
            k8s_uninstall,
            docker_run,
            docker_shell,
            docker_compose,
        ):
            if not hasattr(cls, f.__name__):
                setattr(cls, f.__name__, classmethod(f))
        return cls

    return decorator
