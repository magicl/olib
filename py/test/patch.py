# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from olib.py.utils.obj import rgetattr, rsetattr


@contextmanager
def patchObjectsValues(objs, tupleList: Iterator[tuple[str, Any]]):
    """Will change the values of the given objects properties, and restore them before returning"""
    allOld = []
    for obj in objs:
        old = []
        for name, val in tupleList:
            old.append(rgetattr(obj, name, separator='.'))
            rsetattr(obj, name, val, separator='.')
        allOld.append(old)

    try:
        yield
    finally:
        for old, obj in zip(allOld, objs):
            for (name, val), old_ in zip(tupleList, old):
                # Restore
                rsetattr(obj, name, old_, separator='.')


@contextmanager
def patchAddObjectAttr(obj, attrName, value):
    """Adds an attribute to the object, and deletes it when done"""
    assert not hasattr(obj, attrName)  # nosec: assert_used

    setattr(obj, attrName, value)

    try:
        yield
    finally:
        delattr(obj, attrName)
