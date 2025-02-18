# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~
import fnmatch
import io
import logging
import os
import re
from contextlib import contextmanager

logger = logging.getLogger(__name__)


@contextmanager
def openOrPassthrough(filenameOrFile: str | bytes | io.IOBase | os.PathLike, mode: str, *args, storage=None, **kwargs):
    """If a string object is received, opens the file. Else, treats it as an in-memory or previously opened file, and passes it through"""
    if isinstance(filenameOrFile, (str, os.PathLike)):
        if storage is None:
            encoding = kwargs.get('encoding', 'utf-8' if mode in ('r', 'w', 'rt', 'wt') else None)

            with open(filenameOrFile, mode, encoding=encoding) as f:
                yield f
        else:
            with storage.open(filenameOrFile, mode, *args, **kwargs) as f:
                yield f

    else:
        # Already a file
        yield filenameOrFile


def acceptableFilename(name, lower=True):
    """Returns an acceptable filename from a string. Removes special characters etc"""
    if lower:
        name = name.lower()
    name = re.sub(r'[\s,]+', '-', name)
    name = re.sub(r'[^\w\-\.]+', '', name)

    return name


def dir_has_files(directory, *match):
    for _, _, files in os.walk(directory):
        for file in files:
            if any(fnmatch.fnmatch(file, m) for m in match):
                return True
    return False
