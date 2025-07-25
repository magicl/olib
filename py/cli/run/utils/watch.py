# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~
from collections.abc import Callable

import sh


def watch_files(path: str, cwd: str, func: Callable[[], None], run_on_start: bool = True) -> None:
    """
    Watch a path for changes and run a function when it changes
    """

    if run_on_start:
        try:
            func()
        except sh.ErrorReturnCode:
            # Ignore build errors. Keep listening
            pass

    try:
        for line in sh.inotifywait('-m', '-r', '-e', 'close_write', path, _cwd=cwd, _iter=True):
            print('Updated: ', line)
            try:
                func()
            except sh.ErrorReturnCode:
                # Ignore build errors. Keep listening
                continue

    except KeyboardInterrupt:
        print('Stopping watch')
