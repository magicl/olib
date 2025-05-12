# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~

"""Provides information about execution environment"""

import os
import sys
from collections.abc import Callable
from contextlib import contextmanager
from enum import Enum
from typing import Any, TypeVar

T = TypeVar('T')


class SanityCheckError(Exception):
    pass


class ExecEnv(Enum):
    local = 1
    docker = 2
    k8s = 3
    vagrant = 4
    jenkins = 5
    unknown = 99


class ExecInv(Enum):
    django = 1  # ./manage.py
    pylint = 2
    celery = 3
    gunicorn = 4
    cli = 5
    strawberry = 6
    unknown = 99


class ExecContext(Enum):
    web = 1
    test = 3
    pylint = 6
    migration = 7
    celery_worker = 8
    celery_beat = 9
    django_command = 10
    unknown = 99


_execEnv = ExecEnv.unknown
_execInv = ExecInv.unknown
_execContext = ExecContext.unknown

_isEnvCli = False
_isEnvCliQuiet = False
_isEnvCron = False


@contextmanager
def cliEnv(quiet=False):
    """Makes isEnvCli return true for code within context"""
    global _isEnvCli, _isEnvCliQuiet  # pylint: disable=global-statement
    oldQuiet = _isEnvCliQuiet

    _isEnvCli = True
    _isEnvCliQuiet = quiet

    yield

    _isEnvCli = False
    _isEnvCliQuiet = oldQuiet


@contextmanager
def cronEnv():
    """Makes isEnvCron true for code within context"""
    global _isEnvCron  # pylint: disable=global-statement

    _isEnvCron = True
    yield
    _isEnvCron = False


def isEnvCelery():
    return _execInv == ExecInv.celery


def isEnvWeb():
    return _execContext == ExecContext.web


def isEnvProduction():
    # Simple for now.. k8s == production.
    return _execEnv == ExecEnv.k8s


def isEnvTest():
    return _execContext == ExecContext.test


def isEnvCron():
    return _isEnvCron


def isEnvCli():
    return _isEnvCli


def isEnvLocal():
    return _execEnv == ExecEnv.local and _execInv == ExecInv.django


def isEnvCliNonQuiet():
    return _isEnvCli and not _isEnvCliQuiet


def _isDocker():
    try:
        with open('/proc/1/cgroup', encoding='utf-8') as ifh:
            return 'docker' in ifh.read()
    except FileNotFoundError:
        return False


def _isK8S():
    """
    k8s -> pod: returns "k8s"
    k8s -> jenkins: identifies as "jenkins", not "k8s"
    """
    return os.path.isfile('/var/run/secrets/kubernetes.io/serviceaccount/namespace') and not _isJenkins()


def _isDjango():
    return sys.argv[0].endswith('manage.py')


def _isGunicorn():
    return sys.argv[0].endswith('gunicorn')


def _isStrawberry():
    return sys.argv[0].endswith('strawberry')


def _isPylint():
    return sys.argv[0].endswith('pylint')


def _isCelery():
    return sys.argv[0].endswith('celery')


def _isJenkins():
    return 'JENKINS_URL' in os.environ


def _isVagrant():
    return os.path.isfile('/var/log/inside_vagrant')


def _pickOne(what: str, *options: tuple[T | None, Callable], default: T | None = None) -> T:
    result = set()
    for val, func in options:
        if val is None:
            # func returns values to add
            result |= func()
        elif func():
            # func returns true if we are adding
            result.add(val)

    if not result and default is not None:
        result.add(default)

    if len(result) == 1:
        return next(iter(result))

    print(f"Unknown {what}\n{sys.argv=}")
    raise Exception(f"Unknown {what}: {result}")


def _isContextWeb():
    return len(sys.argv) > 1 and sys.argv[1] == 'runserver' or os.environ.get('ENTRYPOINT') in ('web-server',)


def _getManagePyContext():
    if len(sys.argv) > 1 and _isDjango():
        if sys.argv[1] == 'runserver':
            return {ExecContext.web}
        if sys.argv[1] == 'test':
            return {ExecContext.test}
        if sys.argv[1] == 'migrate':
            return {ExecContext.migration}
        return {ExecContext.django_command}
    return set()


def _getCeleryContext():
    if len(sys.argv) > 1 and _isCelery():
        # Expect: celery -A {app} worker/beat
        if sys.argv[3] == 'worker':
            return {ExecContext.celery_worker}
        if sys.argv[3] == 'beat':
            return {ExecContext.celery_beat}
    return set()


def _get_exception_info():
    """Helper for debugging unknown context errors"""
    return f"{sys.argv=}"


# def _isContextMigrate():
#    return len(sys.argv) > 1 and sys.argv[1] == 'migrate'

# def _isContextCollectstatic():
#    return len(sys.argv) > 1 and sys.argv[1] == 'collectstatic'


def initExecEnv(execEnvOverride=None, execContextOverride=None, ignoreSanityChecks=False):
    global _execEnv, _execContext  # pylint: disable=global-statement

    _execEnv = _pickOne(
        'execution environment',
        (ExecEnv.docker, _isDocker),
        (ExecEnv.k8s, _isK8S),
        (ExecEnv.vagrant, _isVagrant),
        (ExecEnv.jenkins, _isJenkins),
        default=ExecEnv.local,
    )

    _execInv = _pickOne(
        'execution invocation',
        (ExecInv.django, _isDjango),
        (ExecInv.pylint, _isPylint),
        (ExecInv.celery, _isCelery),
        (ExecInv.gunicorn, _isGunicorn),
        (ExecInv.cli, isEnvCli),
        (ExecInv.strawberry, _isStrawberry),
    )

    _execContext = _pickOne(
        'execution context',
        (ExecContext.web, _isContextWeb),
        (ExecContext.pylint, _isPylint),
        (None, _getManagePyContext),
        (None, _getCeleryContext),
        default=ExecContext.unknown,
    )

    # Overrides
    # Only allow overrides in testing context
    if execEnvOverride is not None:
        if _execContext != ExecContext.test:
            raise Exception('Can only override environment during testing')

        _execEnv = execEnvOverride

    if execContextOverride is not None:
        if _execContext != ExecContext.test:
            raise Exception('Can only override environment during testing')

        _execContext = execContextOverride

    # SANITY / SAFETY CHECKS
    if not ignoreSanityChecks:
        if _execEnv == ExecEnv.k8s:
            if os.environ.get('DEBUG') != 'false':
                raise SanityCheckError('Running on k8s and DEBUG is not set to False')

            if _execContext in (ExecContext.unknown, ExecContext.test):
                raise SanityCheckError(
                    f'Running on k8s with "{_execContext}" execution context. ({_get_exception_info()})'
                )
