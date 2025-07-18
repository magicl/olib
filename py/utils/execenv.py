# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~

"""Provides information about execution environment"""

import os
import sys
from collections.abc import Callable, Generator
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
    uvicorn = 5
    cli = 6
    strawberry = 7
    mypy = 8
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
def cliEnv(quiet: bool = False) -> Generator[None, None, None]:
    """Makes isEnvCli return true for code within context"""
    global _isEnvCli, _isEnvCliQuiet  # pylint: disable=global-statement
    oldQuiet = _isEnvCliQuiet

    _isEnvCli = True
    _isEnvCliQuiet = quiet

    yield

    _isEnvCli = False
    _isEnvCliQuiet = oldQuiet


@contextmanager
def cronEnv() -> Generator[None, None, None]:
    """Makes isEnvCron true for code within context"""
    global _isEnvCron  # pylint: disable=global-statement

    _isEnvCron = True
    yield
    _isEnvCron = False


def isEnvCelery() -> bool:
    return _execInv == ExecInv.celery


def isEnvWeb() -> bool:
    return _execContext == ExecContext.web


def isEnvProduction() -> bool:
    # Simple for now.. k8s == production.
    return _execEnv == ExecEnv.k8s


def isEnvTest() -> bool:
    return _execContext == ExecContext.test


def isEnvCron() -> bool:
    return _isEnvCron


def isEnvCli() -> bool:
    return _isEnvCli


def isEnvLocal() -> bool:
    return _execEnv == ExecEnv.local and _execInv == ExecInv.django


def isEnvCliNonQuiet() -> bool:
    return _isEnvCli and not _isEnvCliQuiet


def _isDocker() -> bool:
    try:
        with open('/proc/1/cgroup', encoding='utf-8') as ifh:
            return 'docker' in ifh.read()
    except FileNotFoundError:
        return False


def _isK8S() -> bool:
    """
    k8s -> pod: returns "k8s"
    k8s -> jenkins: identifies as "jenkins", not "k8s"
    """
    return os.path.isfile('/var/run/secrets/kubernetes.io/serviceaccount/namespace') and not _isJenkins()


def _isDjango() -> bool:
    return sys.argv[0].endswith('manage.py')


def _isGunicorn() -> bool:
    return sys.argv[0].endswith('gunicorn')


def _isUvicorn() -> bool:
    return sys.argv[0].endswith('uvicorn')


def _isStrawberry() -> bool:
    return sys.argv[0].endswith('strawberry')


def _isPylint() -> bool:
    return sys.argv[0].endswith('pylint')


def _isMypy() -> bool:
    return sys.argv[0].endswith('mypy')


def _isCelery() -> bool:
    return sys.argv[0].endswith('celery')


def _isJenkins() -> bool:
    return 'JENKINS_URL' in os.environ


def _isVagrant() -> bool:
    return os.path.isfile('/var/log/inside_vagrant')


def _pickOne(what: str, *options: tuple[T | None, Callable[[], Any]], default: T | None = None) -> T:
    result: set[T] = set()
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


def _isContextWeb() -> bool:
    return len(sys.argv) > 1 and sys.argv[1] == 'runserver' or os.environ.get('ENTRYPOINT') in ('web-server',)


def _getManagePyContext() -> set[ExecContext]:
    if len(sys.argv) > 1 and _isDjango():
        if sys.argv[1] == 'runserver':
            return {ExecContext.web}
        if sys.argv[1] == 'test':
            return {ExecContext.test}
        if sys.argv[1] == 'migrate':
            return {ExecContext.migration}
        return {ExecContext.django_command}
    return set()


def _getCeleryContext() -> set[ExecContext]:
    if len(sys.argv) > 1 and _isCelery():
        # Expect: celery -A {app} worker/beat
        if sys.argv[3] == 'worker':
            return {ExecContext.celery_worker}
        if sys.argv[3] == 'beat':
            return {ExecContext.celery_beat}
    return set()


def _get_exception_info() -> str:
    """Helper for debugging unknown context errors"""
    return f"{sys.argv=}"


# def _isContextMigrate():
#    return len(sys.argv) > 1 and sys.argv[1] == 'migrate'

# def _isContextCollectstatic():
#    return len(sys.argv) > 1 and sys.argv[1] == 'collectstatic'


def initExecEnv(
    execEnvOverride: ExecEnv | None = None,
    execContextOverride: ExecContext | None = None,
    ignoreSanityChecks: bool = False,
) -> None:
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
        (ExecInv.mypy, _isMypy),
        (ExecInv.celery, _isCelery),
        (ExecInv.gunicorn, _isGunicorn),
        (ExecInv.uvicorn, _isUvicorn),
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
