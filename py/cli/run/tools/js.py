# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~

# pylint: disable=duplicate-code

import os
from functools import cache

import click
import sh

from ....utils.file import dir_has_files
from ....utils.listutils import groupByValue

# def pre_commit(cmd, files):
#    fileStr = '--all-files' if not files else f"--files {' '.join(files)}"
#    sh.bash('-c', f"pre-commit run {cmd} {fileStr}", _fg=True)


@cache
def find_package_json_dir(directory):
    """Find closest package.json. Cached to prevent unnecessary lookups"""
    if directory == '':
        directory = '.'

    if os.path.exists(f'{directory}/package.json'):
        return directory
    if directory == '.':
        return None

    return find_package_json_dir(os.path.dirname(directory))


def register(config):
    @click.group()
    def js():
        pass

    if 'javascript' in config.tools:

        @js.command()
        @click.argument('files', nargs=-1, type=click.Path())
        @click.pass_context
        def lint(ctx, files):
            """Run eslint in all package.js directories in scope"""
            if not files:
                if ctx.obj.meta.isOlib:
                    files = ['js']  # All python code is in the js
                else:
                    files = [
                        f.name
                        for f in os.scandir('.')
                        if f.is_dir()
                        and not f.name.startswith('.')
                        and f.name != 'olib'
                        and dir_has_files(f.name, '*.js', '*.ts', '*.tsx', '*.mjs')
                    ] + ['*.js', '*.ts', '*.tsx', '*.mjs']

            # For each file, find closest package.json, so we can run lint in that scope
            by_dir = groupByValue(files, keyFunc=find_package_json_dir)

            for dir, _ in by_dir.items():
                if dir is None:
                    continue

                # files = [f.removeprefix(dir).removeprefix('/') or '.' for f in files]
                # print(files)
                # print(f'Linting {dir}')

                sh.bash(
                    '-c',
                    """
                    nice npm run lint .
                    """,
                    _fg=True,
                    _env=os.environ,
                    _cwd=dir,
                )

        @js.command()
        @click.option('--no-ui', default=False, is_flag=True)
        @click.pass_context
        def test_unit(ctx, no_ui):
            # Keep it simple for now
            dir = 'frontend'

            env = {**os.environ}
            if no_ui:
                env['CI'] = '1'

            sh.bash(
                '-c',
                """
                nice npm run test
                """,
                _fg=True,
                _env=env,
                _cwd=dir,
            )

        @js.command()
        @click.option('--no-ui', default=False, is_flag=True)
        @click.pass_context
        def test_integration(ctx, no_ui):
            # Keep it simple for now
            dir = 'frontend'

            env = {**os.environ}
            if no_ui:
                env['CI'] = '1'

            sh.bash(
                '-c',
                """
                nice npm run test:playwright
                """,
                _fg=True,
                _env=env,
                _cwd=dir,
            )

        @js.command()
        @click.pass_context
        def tsc(ctx):
            # Keep it simple for now
            dir = 'frontend'

            sh.bash(
                '-c',
                """
                nice npm run env -- tsc --noEmit
                """,
                _fg=True,
                _env=os.environ,
                _cwd=dir,
            )

        @js.command()
        @click.pass_context
        def chromatic(ctx):
            # Keep it simple for now
            dir = 'frontend'

            sh.bash(
                '-c',
                """
                nice npm run chromatic
                """,
                _fg=True,
                _env=os.environ,
                _cwd=dir,
            )

    if len(js.commands):
        config.meta.commandGroups.append(('js', js))
