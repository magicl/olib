# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~

import glob
import os
import shutil
import signal
import sys

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


def images_build_pre(cls, ctx, k8s=False):
    """
    Override in Config to do work before images are built. Either run actions directly, or set up
    parproc tasks with now=True
    """
    click.echo('  None')


def run_images_build_pre(cls, ctx, k8s=False):
    click.echo('Pre-build Steps For Image...')
    cls.images_build_pre(ctx, k8s=k8s)
    pp.wait_clear(exception_on_failure=True)  # type: ignore


def images_build(cls, ctx, images=None, debug=False, no_pre_build=False, force=False, k8s=False):
    if not no_pre_build:
        run_images_build_pre(cls, ctx, k8s=k8s)

    click.echo('Building Image...')
    meta = ctx.obj.config.meta

    accepted_images = images.split(',') if images is not None else None
    for image_name, dockerfile in meta.build_containers.items():
        if accepted_images is not None and image_name not in accepted_images:
            continue

        options = f"build -t {image_name} -f {dockerfile}"
        if debug:
            options = f"{options} --progress=plain"
        if force:
            options = f"{options} --no-cache"

        sh.bash('-c', f"docker {options} .", _fg=True)


def images_push(cls, ctx, images=None):
    click.echo('Pushing Image...')
    meta = ctx.obj.config.meta
    inst = ctx.obj.inst

    accepted_images = images.split(',') if images is not None else None
    for image_name, _ in meta.build_containers.items():
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


def images_analyze(cls, ctx, images=None):
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

    accepted_images = images.split(',') if images is not None else None
    for image_name, _ in meta.build_containers.items():
        if accepted_images is not None and image_name not in accepted_images:
            continue

        sh.dive(
            f'docker://{inst['pck_registry']}/{meta.build_category}/{meta.build_name}/{image_name}:latest', _fg=True
        )


def k8s_push_config(cls, ctx):
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


def k8s_push_secrets(cls, ctx):
    click.echo('Pushing Secrets to Kubernetes...')
    inst = ctx.obj.inst

    for secret_file_glob_ in inst.get('secret_files', []):
        secret_file_glob = os.path.expandvars(secret_file_glob_)

        secret_files = glob.glob(secret_file_glob)
        for secret_file in secret_files:
            # Secret files have a config-file format, with key=value pairs
            env_vars = dotenv_values(secret_file)

            # Store k8s secrets with the name of the secret file
            secret_name = os.path.basename(secret_file)
            k8s_secret_create_or_update(secret_name, ctx.obj.k8sNamespace, ctx.obj.k8sContext, env_vars)


def k8s_migrate(cls, ctx, break_on_error=False):
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
        sh.helm('uninstall', 'migration', '-n', ctx.obj.k8sNamespace, f'--kube-context={ctx.obj.k8sContext}', _fg=True)

    if not success:
        click.echo('Migrations failed', err=True)
        sys.exit(1)


def k8s_deploy(cls, ctx, deployments):
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


def k8s_uninstall(cls, ctx):
    click.echo('Deleting from Kubernetes...')
    meta = ctx.obj.meta

    if meta.build_helm_deploy is None:
        sh.kubectl(
            'delete', '-f', 'deployment.yml', '-n', ctx.obj.k8sNamespace, f'--context={ctx.obj.k8sContext}', _fg=True
        )

    else:
        sh.helm(
            'uninstall', meta.build_name, '-n', ctx.obj.k8sNamespace, f'--kube-context={ctx.obj.k8sContext}', _fg=True
        )


def docker_run(cls, ctx):
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


def docker_compose(cls, ctx, no_build=False):
    click.echo('Running Docker Compose...')
    meta = ctx.obj.meta

    if meta.build_compose is None:
        raise Exception('buildSingleService.compose not defined')

    # echo "Mounted on http://127.0.0.1:{meta.build_localMountPort}\n---"

    # Temporarily mask SIGINT from python. We only want docker compose to handle it
    original_sigint = signal.signal(signal.SIGINT, signal.SIG_IGN)
    try:
        build_str = '' if no_build else '--build'
        sh.bash(
            '-c',
            f"""
        docker compose -f {meta.build_compose} up {build_str} --abort-on-container-exit --remove-orphans;
        docker compose -f {meta.build_compose} down
        """,
            _fg=True,
            _env={'UID': str(os.getuid()), 'GID': str(os.getgid()), **os.environ},
        )
    except sh.ErrorReturnCode:
        # Error most likely due to SIGINT. Ignore it
        pass
    finally:
        # Restore original SIGINT handler
        signal.signal(signal.SIGINT, original_sigint)


def docker_shell(cls, ctx):
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


def _implementImage():
    @click.group(chain=True)
    @click.pass_context
    def imageGroup(ctx):
        pass

    @imageGroup.command()
    @click.option('--images', help='Comma separated list of image names. All if empty', type=str)
    @click.option('--debug', help='Output all build info', default=False, is_flag=True)
    @click.option('--no-pre-build', help='Skip pre-build step', default=False, is_flag=True)
    @click.option('--force', help='Force build.  Ignore cache', default=False, is_flag=True)
    @click.pass_context
    def build(ctx, images, debug, no_pre_build, force):
        """Build container"""
        ctx.obj.config.images_build(ctx, images=images, debug=debug, no_pre_build=no_pre_build, force=force, k8s=True)

    @imageGroup.command()
    @click.option('--images', help='Comma separated list of image names. All if empty', type=str)
    @click.option('--debug', help='Output all build info', default=False, is_flag=True)
    @click.option('--no-pre-build', help='Skip pre-build step', default=False, is_flag=True)
    @click.pass_context
    def push(ctx, images, debug, no_pre_build):
        """Push container to registry"""
        ctx.obj.config.images_build(ctx, images=images, debug=debug, no_pre_build=no_pre_build, k8s=True)
        ctx.obj.config.images_push(ctx, images=images)

    @imageGroup.command()
    @click.option('--images', help='Comma separated list of image names. All if empty', type=str)
    @click.pass_context
    def analyze(ctx, images):
        """Analyze image"""
        ctx.obj.config.images_analyze(ctx, images=images)

    return imageGroup


def _implementApp():
    @click.group(chain=True)
    @click.pass_context
    def appGroup(ctx):
        pass

    @appGroup.command()
    @click.pass_context
    def pre_build(ctx):
        """Pre-build step"""
        run_images_build_pre(ctx.obj.config, ctx, k8s=True)

    @appGroup.command()
    @click.pass_context
    def push_secrets(ctx):
        """Push secrets to Kubernetes"""
        ctx.obj.config.k8s_push_secrets(ctx)

    @appGroup.command()
    @click.pass_context
    def push_config(ctx):
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
    def deploy(ctx, images, deployments, no_migrate, no_build, no_pre_build):
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
    def migrate(ctx, break_on_error):
        """Deploy container"""
        ctx.obj.config.k8s_push_config(ctx)
        if ctx.obj.meta.django:
            ctx.obj.config.k8s_migrate(ctx, break_on_error)

    @appGroup.command()
    @click.pass_context
    def uninstall(ctx):
        """Uninstall container"""
        ctx.obj.config.k8s_uninstall(ctx)

    return appGroup


def _implementDocker():
    @click.group(chain=True)
    @click.pass_context
    def dockerGroup(ctx):
        pass

    @dockerGroup.command('run')
    @click.option('--no-build', help='Skip build step', default=False, is_flag=True)
    @click.option('--no-pre-build', help='Skip pre-build step', default=False, is_flag=True)
    @click.pass_context
    def run(ctx, no_build, no_pre_build):
        """Run container in docker"""
        if not no_build:
            ctx.obj.config.images_build(ctx, no_pre_build=no_pre_build)
        ctx.obj.config.docker_run(ctx)

    @dockerGroup.command('compose')
    @click.option('--no-build', help='Skip build step', default=False, is_flag=True)
    @click.option('--no-pre-build', help='Skip pre-build step', default=False, is_flag=True)
    @click.pass_context
    def compose(ctx, no_build, no_pre_build):
        """Run container in docker"""
        if not no_pre_build:
            run_images_build_pre(ctx.obj.config, ctx, k8s=False)
        ctx.obj.config.docker_compose(ctx, no_build=no_build)

    @dockerGroup.command('shell')
    @click.pass_context
    def shell(ctx):
        """Run container in docker with shell"""
        ctx.obj.config.docker_shell(ctx)

    return dockerGroup


def buildSingleService(
    name,
    category,
    servicePort,
    localMountPort,
    deployments=None,
    containers: dict | None = None,
    helm_deploy: str | None = None,
    helm_migrate: str | None = None,
    compose: str | None = None,
):
    """
    Injects functions into service Config for building, deploying etc.

    Expects:
    - deployment.yml file containing all kubernetes components
    - deployment should be named {name}-deployment
    - tls secret should be named {name}-tls
    """

    def decorator(cls):
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
                setattr(cls, f.__name__, classmethod(f))  # type: ignore

        return cls

    return decorator
