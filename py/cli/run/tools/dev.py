# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~


import click
import sh


def register(config):
    @click.group()
    def dev():
        pass

    @dev.command()
    @click.argument('files', nargs=-1, type=click.Path())
    @click.pass_context
    def test_all(ctx, files):
        """Run all available tests that make sense"""

        to_run = []

        if 'python' in config.tools:
            to_run += [
                ('py', 'lint'),
                ('py', 'mypy'),
                ('py', 'test'),
                ('py', 'bandit'),
            ]

        if 'javascript' in config.tools:
            to_run += [('js', 'lint')]

        # Find all commands and run
        commands = {}
        for group_name, group in config.meta.commandGroups:
            if isinstance(group, click.Group):
                for cmd_name, cmd in group.commands.items():
                    commands[(group_name, cmd_name)] = cmd

        failed = []
        for group_name, cmd_name in to_run:
            click.echo(f"Running {group_name}:{cmd_name}")

            # Pass in file arg if command needs it
            args = {}
            key = (group_name, cmd_name)
            if any(arg.name == 'files' for arg in commands[key].params):
                args['files'] = files

            try:
                ctx.invoke(commands[key], **args)
            except sh.ErrorReturnCode:
                failed.append(key)

        if failed:
            for group_name, cmd_name in failed:
                click.echo(f"Failed: {group_name}:{cmd_name}")

            raise click.ClickException('Some tests failed')

    config.meta.commandGroups.append(('dev', dev))