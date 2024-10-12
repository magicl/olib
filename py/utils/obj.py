# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~


def rgetattr(obj, name, default=None, separator='__'):
    """Recursive getattr, using __ to separate fields"""
    nameSplit = name.split(separator)
    for ns in nameSplit:
        try:
            obj = getattr(obj, ns)
        except AttributeError:
            return default
    return obj


def rsetattr(obj, name, value, separator='__'):
    """Recursive setattr, using __ to separate fields"""
    nameSplit = name.split(separator)
    # if more than one item in split, use rgetattr to find the last item
    if len(nameSplit) > 1:
        obj = rgetattr(obj, separator.join(nameSplit[:-1]), separator=separator)
    setattr(obj, nameSplit[-1], value)


def elvis(obj, memberName, default=None):
    """Elvis operator, ".?", returns member if the object is not None"""
    return getattr(obj, memberName) if obj is not None else default


def coalesce(*values):
    """Returns first non-none value"""
    for v in values:
        if v is not None:
            return v

    return None
