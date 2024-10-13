#!/usr/bin/env python3
# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~

import sys

import click
import sh

from ...utils.execenv import cliEnv
from ...utils.module import importModuleFromPath
from .cli import GroupTopLevel
from .context import RunContext
from .defaults import Config as defaultConfig
from .templates.base import prep_config
from .tools.dev import register as register_dev
from .tools.js import register as register_js
from .tools.k8s import register as register_k8s
from .tools.py import register as register_py

CLI_CONTEXT_SETTINGS = {'help_option_names': ['-h', '--help']}


def create_cli(config=None):
    if config is None:
        try:
            config = importModuleFromPath('./config.py').Config
        except FileNotFoundError:
            config = defaultConfig

    # Apply any defaults from defaultConfig
    for k, v in vars(defaultConfig).items():
        if not hasattr(config, k):
            setattr(config, k, v)

    @click.group(
        help=f"Command tool for {config.displayName}",
        context_settings=CLI_CONTEXT_SETTINGS,
        cls=GroupTopLevel,
    )
    @click.option(
        '--inst',
        '-i',
        help='Name or alias of inst to apply command to. Default inst is used if none applied',
    )
    @click.option('--cluster', '-c', help='Cluster of inst to apply command to. Can be used in place of --inst')
    @click.pass_context
    def cli(ctx, inst, cluster):
        ctx.obj = RunContext(config, inst, cluster)

    @cli.command()
    @click.pass_context
    def init(ctx):
        sh.bash('-c', f"{ctx.obj.meta.olib_path}/scripts/init.sh", _fg=True)

    @cli.command()
    @click.option('--tool', type=click.Choice(['python', 'javascript']))
    @click.pass_context
    def has(ctx, tool):
        """Check if tool is available"""
        if tool is not None:
            sys.exit(0 if tool in ctx.obj.config.tools else 1)
        sys.exit(1)

    @cli.command()
    @click.option('--license', default=False, is_flag=True)
    @click.pass_context
    def get(ctx, license):
        """Return a value"""
        if license:
            click.echo(ctx.obj.config.license, nl=False)
            sys.exit(0)

        sys.exit(1)

    prep_config(config)

    register_py(config)
    register_js(config)
    register_dev(config)
    register_k8s(config)

    for groupName, group in config.meta.commandGroups:
        cli.add_command(group, name=groupName)

    return cli


def main():
    with cliEnv():
        cli = create_cli()

        try:
            cli()  # pylint: disable=no-value-for-parameter
        except sh.ErrorReturnCode as e:
            print(f"Failed with code {e.exit_code}")
            click.echo(e.stderr, err=True)
            sys.exit(e.exit_code)


if __name__ == '__main__':
    main()
