# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~

# pylint: disable=duplicate-code

import os
import shutil
import sys
from functools import cache

import click
import parproc as pp
import sh

from ....utils.file import dir_has_files
from ....utils.listutils import groupByValue
from ..utils.template import render_template


def pre_commit(cmd, files):
    fileStr = '--all-files' if not files else f"--files {' '.join(files)}"
    sh.bash('-c', f"pre-commit run {cmd} {fileStr}", _fg=True)


@cache
def is_manage_py_dir(directory, django_working_dir_abs):
    if django_working_dir_abs == '.':
        # Whole project is django
        return True

    return os.path.abspath(directory).startswith(django_working_dir_abs)


def register(config):
    @click.group()
    def py():
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
        def lint(ctx, files, quiet):
            """Run pylint"""
            if not files:
                if ctx.obj.meta.isOlib:
                    files = ['py', '*.py']  # All python code is in the py folder
                else:
                    files = [
                        f.name
                        for f in os.scandir('.')
                        if f.is_dir()
                        and not f.name.startswith('.')
                        and f.name != 'olib'
                        and f.name != 'frontend'
                        and dir_has_files(f.name, '*.py')
                    ] + ['*.py']

            # For each file, find closest manage.py. So we can run with or without manage.py
            if ctx.obj.meta.django:
                django_working_dir_abs = os.path.abspath(ctx.obj.meta.django_working_dir)
                by_dir = groupByValue(files, keyFunc=lambda v: is_manage_py_dir(v, django_working_dir_abs))
            else:
                by_dir = {False: files}

            for have_django, files_ in by_dir.items():
                # click.echo(f'{have_django=}, {files_=}', err=True)
                config = render_template(
                    ctx, 'config/pylintrc', {'have_django': have_django}, suffix='.django' if have_django else ''
                )

                sh.bash(
                    '-c',
                    f"""
                    nice pylint --rcfile={config} {'-rn -sn' if quiet else ''} {' '.join(files_)}
                    """,
                    _fg=True,
                    _env=os.environ,
                )

        @py.command()
        @click.argument('files', nargs=-1, type=click.Path())
        @click.option('--no-install-types', default=False, is_flag=True)
        @click.pass_context
        def mypy(ctx, files, no_install_types):
            """Run mypy"""
            if not files:
                if ctx.obj.meta.isOlib:
                    files = ['py', '*.py']  # All python code is in the py folder
                else:
                    files = [
                        f.name
                        for f in os.scandir('.')
                        if f.is_dir()
                        and not f.name.startswith('.')
                        and f.name != 'olib'
                        and f.name != 'frontend'
                        and dir_has_files(f.name, '*.py')
                    ] + ['*.py']

            config = render_template(ctx, 'config/mypy')

            sh.bash(
                '-c',
                f"""
                nice mypy --config-file={config} {'--install-types --non-interactive' if not no_install_types else ''} {' '.join(files)}
                """,
                _fg=True,
                _env=os.environ,
            )

            # pre_commit('mypy', files)

        @py.command()
        @click.argument('files', nargs=-1, type=click.Path())
        def isort(files):
            """Run isort"""
            pre_commit('isort', files)

        @py.command()
        @click.argument('files', nargs=-1, type=click.Path())
        def pyupgrade(files):
            """Run pyupgrade"""
            pre_commit('pyupgrade', files)

        @py.command()
        @click.argument('files', nargs=-1, type=click.Path())
        def black(files):
            """Run black"""
            pre_commit('black', files)

        @py.command()
        @click.argument('files', nargs=-1, type=click.Path())
        def unify(files):
            """Run unify"""
            pre_commit('unify', files)

        @py.command()
        @click.argument('files', nargs=-1, type=click.Path())
        def bandit(files):
            """Run bandit"""
            pre_commit('bandit', files)

        @py.command('license-update')
        @click.argument('files', nargs=-1, type=click.Path())
        def licenseUpdate(files):
            """Run licenseUpdate"""
            pre_commit('license-update', files)

        @py.command()
        @click.argument('files', nargs=-1, type=click.Path())
        def shellcheck(files):
            """Run shellcheck"""
            pre_commit('shellcheck', files)

        def _djangoSetupTasks(ctx, fast):
            if fast:
                return

            # Make sure db is up to date
            @pp.Proc(now=True)  # type: ignore
            def migrate(context):
                sh.python3(ctx.obj.meta.django_manage_py, 'migrate', _cwd=ctx.obj.meta.django_working_dir)

            # @pp.Proc(name='create-admin', deps=['migrate'], now=True)
            # def createAdmin(context):
            #     sh.python3('./sm.py', 'admin-create', 'admin', '', '', '', 'superuser', 'nimda', '--if-no-user')

            # Process / copy all static images etc
            @pp.Proc(now=True)  # type: ignore
            def collect_static(context):
                sh.python3(
                    ctx.obj.meta.django_manage_py,
                    'collectstatic',
                    '-v0',
                    '--noinput',
                    _cwd=ctx.obj.meta.django_working_dir,
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
        def runserver(ctx, fast, tee, tee_to, args):
            """Django runserver. Pass in any arguments you would pass to ./manage.py runserver"""
            if tee:
                os.makedirs(tee_to.rsplit('/', 1)[0], exist_ok=True)

            _djangoSetupTasks(ctx, fast)
            pp.wait_clear(exception_on_failure=True)  # type: ignore

            cmd = sh.python3.bake(
                ctx.obj.meta.django_manage_py,
                'runserver',
                '--nostatic',
                *args,
                _env=os.environ,
                _cwd=ctx.obj.meta.django_working_dir,
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
        def test(ctx, fast, tee, tee_to, coverage, args):
            """Django test. Pass in any arguments you would pass to ./manage.py test"""
            if tee:
                os.makedirs(tee_to.rsplit('/', 1)[0], exist_ok=True)

            if not ctx.obj.config.meta.django:
                print('Tests not implemented for non-django. Fix!')
                sys.exit(0)

            # pp.setOptions(dynamic=sys.stdout.isatty())
            _djangoSetupTasks(ctx, fast)
            pp.wait_clear(exception_on_failure=True)  # type: ignore

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
            if coverage:
                coverage_config = render_template(ctx, 'config/coveragerc')
                env['COVERAGE_FILE'] = '.output/.coverage'

                cmd = sh.coverage.bake(
                    'run',
                    f"--rcfile={coverage_config}",
                    ctx.obj.meta.django_manage_py,
                    'test',
                    *sharedArgs,
                    *args,
                    _env=env,
                    _cwd=ctx.obj.meta.django_working_dir,
                )
            else:
                cmd = sh.python3.bake(
                    *pre_args,
                    ctx.obj.meta.django_manage_py,
                    'test',
                    *sharedArgs,
                    *args,
                    _env=env,
                    _cwd=ctx.obj.meta.django_working_dir,
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
                sh.coverage('report', '-m', _fg=True)
                sh.coverage('html', '--directory=.output/htmlcov', _fg=True)

        @py.command(help='Convert camelCase func/var names to snake_case')
        @click.argument('files', nargs=-1, type=click.Path())
        def fix_camel(files):
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