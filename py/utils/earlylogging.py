# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~

"""Contains primitives that can be used before logging is initialized"""
import logging
import os
import sys

from olib.py.utils.execenv import isEnvTest

cliLevel: int | None = None  # Set via cli -vvv or -v3, or LOG_LEVEL env variable
fileLevel: int | None = None  # Defaults to DEBUG. Set via LOG_LEVEL env variable

_levels = {'debug': logging.DEBUG, 'info': logging.INFO, 'warning': logging.WARNING, 'error': logging.ERROR}


def cliLogLevel() -> int:
    global cliLevel  # pylint: disable=global-statement

    if cliLevel is None:
        if len(sys.argv) > 1:
            verbose: int | None = None

            if '-v3' in sys.argv or '-vvv' in sys.argv:
                verbose = 3
            elif '-v2' in sys.argv or '-vv' in sys.argv:
                verbose = 2
            elif '-v' in sys.argv:
                # Handle e.g. "-v 3"
                pos = sys.argv.index('-v')
                try:
                    verbose = int(sys.argv[pos + 1])
                except ValueError:
                    pass

            if verbose == 3:
                cliLevel = logging.DEBUG
            elif verbose == 2:
                cliLevel = logging.INFO
            elif verbose == 1:
                cliLevel = logging.WARNING
            elif verbose == 0:
                cliLevel = logging.ERROR

        if cliLevel is None:
            if isEnvTest():
                # Default to warning in test environment
                cliLevel = logging.WARNING

            elif (logLevel := os.environ.get('LOG_LEVEL')) is not None:
                try:
                    cliLevel = int(logLevel)
                except ValueError:
                    try:
                        cliLevel = _levels[logLevel]
                    except KeyError:
                        print(f"INVALID LOG_LEVEL IN ENVIRONMENT VARIABLE: {logLevel}")

        # Final default
        if cliLevel is None:
            cliLevel = logging.WARNING

    return cliLevel


def fileLogLevel() -> int:
    global fileLevel  # pylint: disable=global-statement

    if fileLevel is None:
        fileLevel = logging.WARNING

        if (logLevel := os.environ.get('LOG_LEVEL')) is not None:
            try:
                fileLevel = int(logLevel)
            except ValueError:
                try:
                    fileLevel = _levels[logLevel]
                except KeyError:
                    print(f"INVALID LOG_LEVEL IN ENVIRONMENT VARIABLE: {logLevel}")

    return fileLevel


def earlyInfo(str: str) -> None:
    if cliLogLevel() <= logging.INFO:
        print(str)
