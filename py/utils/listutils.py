# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~
import datetime
from collections import defaultdict
from collections.abc import Callable, Generator, Iterable
from typing import Any, TypeVar

from django.utils import timezone

T = TypeVar('T')


def removeDuplicates(seq: Iterable[T]) -> list[T]:
    """Removes duplicats from list while preserving order"""
    seen: set[T] = set()
    seenAdd = seen.add
    return [v for v in seq if not (v in seen or seenAdd(v))]


def extendUnique(seq0: Iterable[T], *other: Iterable[T]) -> list[T]:
    """Extend first sequence with new items from second sequence. Items in other can be None"""
    seen = set(seq0)
    ret = list(seq0)
    for seq in other:
        if seq is not None:
            for v in seq:
                if v not in seen:
                    ret.append(v)
                    seen.add(v)

    return ret


def dropDuplicates(seq: Iterable[T], uniqueFunc: Callable[[T], Any] | None = None) -> list[T]:
    """Remove duplicate items in list"""
    seen: set[Any] = set()
    ret = []
    for s in seq:
        v = s if uniqueFunc is None else uniqueFunc(s)
        if v not in seen:
            ret.append(s)
            seen.add(v)

    return ret


def chunks(l: Iterable[T], n: int) -> Generator[Iterable[T], None, None]:
    """Yield successive n-sized chunks from l."""
    # Need list/tuple to slice
    lst = list(l) if not isinstance(l, (list, tuple)) else l

    for i in range(0, len(lst), n):
        yield lst[i : i + n]


def chunkByMeasure(l: Iterable[T], n: int, measureFunc: Callable[[T], int]) -> Iterable[list[T]]:
    """Chunks, but instead of counting each list item as value 1, each list item is counted as the  value returned by measureFunc when applied on the list item. If any one item
    is larger than n, then it is output in its own chunk, and that chunk can exceed n"""
    lst = list(l) if not isinstance(l, (list, tuple)) else l

    out: list[T] = []
    outSize = 0
    for v in lst:
        size = measureFunc(v)
        if out and outSize + size > n:
            # Adding one more would exceed limit
            yield out
            out = []
            outSize = 0

        out.append(v)
        outSize += size

    # Output remaining
    if out:
        yield out


# Adds defeults to list if the list does not currently have those items
def applyListDefaults(lst: list[T], defaults: list[T]) -> list[T]:
    if len(lst) < len(defaults):
        lst += defaults[len(lst) :]

    for i, v in enumerate(lst):
        if v is None:
            lst[i] = defaults[i]

    return lst


def groupByValue(
    lst: Iterable[T],
    keyFunc: Callable[[T], Any] | None = None,
    valFunc: Callable[[T], Any] | None = None,
    unique: bool = False,
    sort: bool = False,
    sortKey: Callable[[Any], Any] | None = None,
) -> dict[Any, list[T]]:

    ret: dict[Any, list[T]] = defaultdict(list)

    if keyFunc is None:
        keyFunc = lambda x: x

    if valFunc is None:
        for v in lst:
            ret[keyFunc(v)].append(v)
    else:
        for v in lst:
            ret[keyFunc(v)].append(valFunc(v))

    if unique:
        for k, v in ret.items():  # type: ignore
            ret[k] = list(set(v))  # type: ignore

    if sort:
        for k, v in ret.items():  # type: ignore
            v.sort(key=sortKey)  # type: ignore

    return ret


def groupByValueMaintainingOrder(
    lst: Iterable[T], keyFunc: Callable[[T], Any], valFunc: Callable[[T], Any] | None = None
) -> list[tuple[Any, list[T]]]:
    """Returns a list of groupings ensuring the overall order is still the same"""
    ret: list[tuple[Any, list[T]]] = []  # outer list
    sub: list[T] = []  # current sub-list
    curKey: Any | None = None

    for v in lst:
        key = keyFunc(v)
        if valFunc is not None:
            v = valFunc(v)  # intentional override of loop variable, so pylint: disable=redefined-loop-name

        if curKey in (None, key):
            sub.append(v)
            curKey = key
            continue

        # Not match. Start new group
        ret.append((curKey, sub))
        sub = [v]
        curKey = key

    if curKey is not None:
        ret.append((curKey, sub))

    return ret


# Group items by month
def groupByMonth(items: Iterable[T], key: str = 'created_at', dayDelta: int = 0) -> list[int]:
    from ..utils.date import defaultTimezone

    commonStartDate = defaultTimezone(datetime.datetime(2017, 1, 1))
    now = timezone.now()
    totMonths = (
        (now.month + now.year * 12) - (commonStartDate.month + commonStartDate.year * 12) + 1
    )  # Number of months for shopments

    monthItems = [0] * totMonths

    for p in items:
        d = getattr(p, key) + datetime.timedelta(days=dayDelta)
        monthItems[(d.month + d.year * 12) - (commonStartDate.month + commonStartDate.year * 12) - 1] += 1

    return monthItems


def splitList(lst: Iterable[T], cond: Callable[[T], bool]) -> tuple[list[T], list[T]]:
    """Returns two lists, the first one for any items where condition is true, and the second for any false condition items"""
    trueVals: list[T] = []
    falseVals: list[T] = []
    for v in lst:
        if cond(v):
            trueVals.append(v)
        else:
            falseVals.append(v)

    return trueVals, falseVals


def firstOrDefault(lst: list[T], default: T) -> T:
    """Returns first element if list is not empty. Else returns default"""
    if lst:
        return lst[0]
    return default


def grouped(iterable: Iterable[T], n: int) -> Iterable[tuple[T, ...]]:
    """
    s -> (s0,s1,s2,...sn-1), (sn,sn+1,sn+2,...s2n-1), (s2n,s2n+1,s2n+2,...s3n-1), ...

    I.e. call with 2 to iterate [1, 2, 3, 4] as [(1, 2), (3, 4)]
    """
    return zip(*[iter(iterable)] * n)
