# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~

# pylint: disable=duplicate-code

import os
import shutil
import sys
from collections.abc import Callable, Sequence
from typing import Any

import click
import parproc as pp
import sh

from ....utils.file import dir_has_files
from ..templates.django_ import DjangoConfig
from ..utils.template import render_template

type FilenameFilter = Callable[[str], bool]


def find_py_root_dir(file_path: str, configs: list[DjangoConfig]) -> tuple[str, DjangoConfig | None]:
    """Find the Python root directory for a given file path.

    Checks if the file is within any of the configured Django roots.

    Args:
        file_path: Path to a file
        configs: List of Django configurations

    Returns:
        tuple: (root_path, config) where:
            - root_path: The root directory path (relative to cwd)
            - config: The Django config for the root directory, or None if no config is found
    """
    file_path = os.path.abspath(file_path)

    # Check if file is within any Django root
    for config in configs:
        config_abs_path = os.path.abspath(config.working_dir)
        if file_path.startswith(config_abs_path):
            return config.working_dir, config

    # If not in any Django root, return current directory as non-Django root
    return '.', None


def group_files_by_root(
    files: list[str], configs: list[DjangoConfig]
) -> dict[tuple[str, DjangoConfig | None], list[str]]:
    """Group files by their Python root directory.

    Args:
        files: List of file paths to group

    Returns:
        dict: {(root_path, config): [file_paths]} mapping root directories to their files
    """
    groups: dict[tuple[str, DjangoConfig | None], list[str]] = {}

    for file_path in files:
        root_path, config = find_py_root_dir(file_path, configs)
        key = (root_path, config)

        if key not in groups:
            groups[key] = []
        groups[key].append(file_path)

    return groups


def discover_all_roots(configs: list[DjangoConfig]) -> list[tuple[str, DjangoConfig | None]]:
    """Discover all Python root directories from the Django configurations.

    Returns:
        list: [(root_path, config)] tuples for all discovered roots
        All paths are relative to the current working directory
    """
    roots: list[tuple[str, DjangoConfig | None]] = []

    # Add all Django roots from configs
    for config in configs:
        roots.append((config.working_dir, config))

    # Add current directory as non-Django root if no Django root exists at "."
    if not any(r[0] == '.' for r in roots):
        roots.append(('.', None))

    return roots


def list_py_dirs(
    root_path: str, exclude_dirs: list[str], filename_match: str = '*.py', dir_default: str | None = '*.py'
) -> list[str]:
    dir_list = []

    for f in os.scandir(root_path):
        if (
            f.is_dir()
            and not f.name.startswith('.')
            and f.name not in ['olib', 'node_modules', '.venv']
            and f.name not in [os.path.basename(d) for d in exclude_dirs]
            and dir_has_files(f.path, filename_match)
        ):
            dir_list.append(f.name)

    if dir_default:
        dir_list = dir_list + [dir_default]

    return dir_list


def get_py_file_groups(
    files: list[str], configs: list[DjangoConfig], filename_match: str = '*.py', dir_default: str | None = '*.py'
) -> dict[tuple[str, DjangoConfig | None], list[str]]:
    if not files:
        # No files specified - discover all roots and use them as groups
        roots = discover_all_roots(configs)
        groups: dict[tuple[str, DjangoConfig | None], list[str]] = {}

        django_dirs = [d for d, config in roots if config is not None]
        for root_path, config in roots:
            dirs = list_py_dirs(root_path, django_dirs, filename_match, dir_default=dir_default)
            if dirs:
                groups[(root_path, config)] = dirs

    else:
        # Files specified - group them by their root directories
        groups = group_files_by_root(files, configs)

    return groups


def pre_commit(cmd: str, files: Sequence[str]) -> None:
    fileStr = '--all-files' if not files else f"--files {' '.join(files)}"
    sh.bash('-c', f"pre-commit run {cmd} {fileStr}", _fg=True)


def register(config: Any) -> None:
    @click.group()
    def py() -> None:
        pass

    if 'python' in config.tools:
        # Add python tools

        @py.command()
        @click.argument('files', nargs=-1, type=click.Path())
        @click.option(
            '--quiet',
            default=False,
            is_flag=True,
            help="Only display messages. Don't display score",
        )
        @click.pass_context
        def lint(ctx: click.Context, files: list[str], quiet: bool) -> None:
            """Run pylint"""
            # if ctx.obj.meta.isOlib:
            #    # All python code is in the py folder
            #    files = ['py', '*.py']

            groups = get_py_file_groups(files, ctx.obj.meta.django)

            # Run lint on all groups
            for (root_path, config), files_list in groups.items():
                if not files_list:
                    continue

                pylintrc_path = render_template(
                    ctx,
                    'config/pylintrc',
                    {'django_config': config},
                    suffix=f'.django.{config.hash()}' if config is not None else '',
                )

                print(f'Pylint {root_path} : {files_list} {'[django]' if config is not None else ''} {pylintrc_path}')
                print('=======================================================================================')

                sh.bash(
                    '-c',
                    f"""
                    nice pylint --rcfile={pylintrc_path} {'-rn -sn' if quiet else ''} {' '.join(files_list)}
                    """,
                    _fg=True,
                    _env=(
                        {
                            **os.environ,
                            'PYTHONPATH': f'{os.environ.get('PYTHONPATH', '')}:{root_path}',
                            'DJANGO_SETTINGS_MODULE': config.settings,
                        }
                        if config is not None
                        else os.environ
                    ),
                )

        @py.command()
        @click.argument('files', nargs=-1, type=click.Path())
        @click.option('--no-install-types', default=False, is_flag=True)
        @click.option('--daemon', '-d', default=False, is_flag=True)
        @click.pass_context
        def mypy(ctx: click.Context, files: list[str], no_install_types: bool, daemon: bool) -> None:
            """Run mypy"""
            groups = get_py_file_groups(files, ctx.obj.meta.django)

            # Config puts mypy cache in .output
            os.makedirs('.output', exist_ok=True)
            # click.echo('CLEARING MYPY CACHE (mypy has been craching on me a lot)')
            # sh.rm('-rf', '.output/.mypy_cache')

            cmd = 'dmypy start --' if daemon else 'nice mypy'
            exclude = '--exclude=.*/olib/.*'

            # Run mypy on all groups
            for (root_path, config), files_list in groups.items():
                if not files_list:
                    continue

                mypyrc_path = render_template(
                    ctx,
                    'config/mypy',
                    {'django_config': config},
                    suffix=f'.django.{config.hash()}' if config is not None else '',
                )

                print(f'Mypy {root_path} : {files_list} {'[django]' if config is not None else ''} {mypyrc_path}')
                print('=======================================================================================')

                sh.bash(
                    '-c',
                    f"""
                    {cmd} --config-file={mypyrc_path} {'--install-types --non-interactive' if not no_install_types and not daemon else ''} {exclude} {' '.join(files_list)}
                    """,
                    _fg=True,
                    _env=(
                        {
                            **os.environ,
                            'PYTHONPATH': f'{os.environ.get('PYTHONPATH', '')}:{root_path}',
                            'DJANGO_SETTINGS_MODULE': config.settings,
                        }
                        if config is not None
                        else os.environ
                    ),
                )

        @py.command()
        @click.argument('files', nargs=-1, type=click.Path())
        def isort(files: tuple[str, ...]) -> None:
            """Run isort"""
            pre_commit('isort', files)

        @py.command()
        @click.argument('files', nargs=-1, type=click.Path())
        def pyupgrade(files: tuple[str, ...]) -> None:
            """Run pyupgrade"""
            pre_commit('pyupgrade', files)

        @py.command()
        @click.argument('files', nargs=-1, type=click.Path())
        def black(files: tuple[str, ...]) -> None:
            """Run black"""
            pre_commit('black', files)

        @py.command()
        @click.argument('files', nargs=-1, type=click.Path())
        def unify(files: tuple[str, ...]) -> None:
            """Run unify"""
            pre_commit('unify', files)

        @py.command()
        @click.argument('files', nargs=-1, type=click.Path())
        def bandit(files: tuple[str, ...]) -> None:
            """Run bandit"""
            pre_commit('bandit', files)

        @py.command('license-update')
        @click.argument('files', nargs=-1, type=click.Path())
        def licenseUpdate(files: tuple[str, ...]) -> None:
            """Run licenseUpdate"""
            pre_commit('license-update', files)

        @py.command()
        @click.argument('files', nargs=-1, type=click.Path())
        def shellcheck(files: tuple[str, ...]) -> None:
            """Run shellcheck"""
            pre_commit('shellcheck', files)

        def _djangoSetupTasks(ctx: click.Context, fast: bool) -> None:
            if fast:
                return

            # Make sure db is up to date
            for config in ctx.obj.meta.django:

                @pp.Proc(now=True, name=f'migrate:{config.name()}')  # type: ignore[misc]
                def migrate(context: Any, config: DjangoConfig = config) -> None:
                    sh.python3(config.manage_py, 'migrate', _cwd=config.working_dir)

            # @pp.Proc(name='create-admin', deps=['migrate'], now=True)
            # def createAdmin(context):
            #     sh.python3('./sm.py', 'admin-create', 'admin', '', '', '', 'superuser', 'nimda', '--if-no-user')

            # Process / copy all static images etc
            for config in ctx.obj.meta.django:
                if not config.collectstatic:
                    continue

                @pp.Proc(now=True, name=f'collect-static:{config.name()}')  # type: ignore[misc]
                def collectstatic(context: Any, config: DjangoConfig = config) -> None:
                    sh.python3(
                        config.manage_py,
                        'collectstatic',
                        '-v0',
                        '--noinput',
                        _cwd=config.working_dir,
                    )

            # @pp.Proc(name='kill-existing-servers', now=True)
            # def killExistingServers(context):
            #     sh.bash('-c', 'scripts/utils/kill_ports.py 8000,9050,15100,15200,15300,15400,15500,15600,15700,16000,16100,16200')

        @py.command(context_settings={'ignore_unknown_options': True})
        @click.option('--fast', default=False, is_flag=True)
        @click.option('--tee', default=False, is_flag=True)
        @click.option('--tee-to', default='.output/debug.runserver.txt')
        @click.argument('args', nargs=-1)
        @click.pass_context
        def runserver(ctx: click.Context, fast: bool, tee: bool, tee_to: str, args: tuple[str, ...]) -> None:
            """Django runserver. Pass in any arguments you would pass to ./manage.py runserver"""
            if tee:
                os.makedirs(tee_to.rsplit('/', 1)[0], exist_ok=True)

            _djangoSetupTasks(ctx, fast)
            pp.wait_clear(exception_on_failure=True)

            config = ctx.obj.meta.django[0] if ctx.obj.meta.django else None
            if config is None:
                print('Runserver not implemented for non-django. Fix!')
                sys.exit(0)

            cmd = sh.python3.bake(
                config.manage_py,
                'runserver',
                '--nostatic',
                *args,
                _env=os.environ,
                _cwd=config.working_dir,
            )

            if tee:
                sh.tee(
                    tee_to,
                    _in=cmd(_piped=True, _err_to_out=True),
                    _out=sys.stdout,
                    _err=sys.stderr,
                )
            else:
                cmd(_fg=True)

        @py.command(context_settings={'ignore_unknown_options': True})
        @click.option('--fast', default=False, is_flag=True)
        @click.option('--tee', default=False, is_flag=True)
        @click.option('--tee-to', default='.output/debug.test.txt')
        @click.option('--coverage', default=False, is_flag=True)
        @click.argument('args', nargs=-1)
        @click.pass_context
        def test(ctx: click.Context, fast: bool, tee: bool, tee_to: str, coverage: bool, args: tuple[str, ...]) -> None:
            """Django test. Pass in any arguments you would pass to ./manage.py test"""
            if tee:
                os.makedirs(tee_to.rsplit('/', 1)[0], exist_ok=True)

            groups = get_py_file_groups([], ctx.obj.meta.django, filename_match='test_*.py', dir_default=None)
            django_configs = [g[1] for g, _ in groups.items() if g[1] is not None]

            if django_configs:
                # We have django tests. initialize them
                _djangoSetupTasks(ctx, fast)
                pp.wait_clear(exception_on_failure=True)

            else:
                raise Exception('Currently need django in project to run tests')

            # if fast:
            #    args = (*args, '--keepdb')
            sharedArgs = ['--testrunner=olib.py.django.test.runner.OTestRunner']

            if not ctx.obj.meta.isOlib:
                # Don't test olib when not in olib, as olib test models will not be available. Cannot use tags, as failures happen
                # on import
                sharedArgs.append(r'--exclude-dir-regexp=/olib/')

            pre_args = []
            if coverage:
                coverage_config = render_template(ctx, 'config/coveragerc')
                pre_args += ['coverage', 'run', f"--rcfile={coverage_config}"]

            env = os.environ
            for (root_path, django_config_), _ in groups.items():
                # If it is not a django test, use the first django to run the test anyway..
                django_config = django_config_ if django_config_ is not None else django_configs[0]
                manage_py = os.path.abspath(os.path.join(django_config.working_dir, django_config.manage_py))

                if coverage:
                    coverage_config = render_template(ctx, 'config/coveragerc')
                    env['COVERAGE_FILE'] = '.output/.coverage'

                    cmd = sh.coverage.bake(
                        'run',
                        f"--rcfile={coverage_config}",
                        manage_py,
                        'test',
                        *sharedArgs,
                        *args,
                        _env=env,
                        _cwd=root_path,
                    )
                else:
                    cmd = sh.python3.bake(
                        *pre_args,
                        manage_py,
                        'test',
                        *sharedArgs,
                        *args,
                        _env=env,
                        _cwd=root_path,
                    )

                if tee:
                    sh.tee(
                        tee_to,
                        _in=cmd(_piped=True, _err_to_out=True),
                        _out=sys.stdout,
                        _err=sys.stderr,
                    )
                else:
                    cmd(_fg=True)

            if coverage:
                sh.coverage('combine', _fg=True)
                sh.coverage('report', '-m', _fg=True)
                sh.coverage('html', '--directory=.output/htmlcov', _fg=True)

        @py.command(help='Convert camelCase func/var names to snake_case')
        @click.argument('files', nargs=-1, type=click.Path())
        def fix_camel(files: tuple[str, ...]) -> None:
            # Install package if needed
            sh.uv('pip', 'install', 'camel-snake-pep8', '--upgrade')
            try:
                # Run it
                sh.Command('camel-snake-pep8')('--yes-to-all', '.', files, _fg=True)
            finally:
                # Clean up
                shutil.rmtree('.ropeproject')

    if len(py.commands):
        config.meta.commandGroups.append(('py', py))
