# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~

import csv
import io
from collections.abc import Iterable
from contextlib import contextmanager
from typing import Any

import pandas as pd

from .file import openOrPassthrough


@contextmanager
def readCSV(
    filenameOrFile,
    headerRowFirst=None,
    skipRows=0,
    storage=None,
    yieldIterator=False,
    delimiter=',',
):
    """Convenience class for reading CSVs"""
    # False positive, as we are returning the generator here, not iterating over it
    # pylint: disable=contextmanager-generator-missing-cleanup
    with openOrPassthrough(filenameOrFile, 'rb', storage=storage) as f:
        # Some text files have a UTF BOM, i.e. bytes EF BB BF at the beginning. Process input to remove BOM
        data = f.read()
        text = data.decode('utf-8-sig') if isinstance(data, bytes) else data
        reader = csv.reader(io.StringIO(text), delimiter=delimiter)

        # Find columns from first row
        iterator = iter(reader)

        if yieldIterator:
            yield iterator
        else:
            # Shared implementation with CSV files
            yield iterCSV(iterator, headerRowFirst, skipRows)

    # pylint: enable=contextmanager-generator-missing-cleanup


def iterCSV(iterator, headerRowFirst=None, skipRows=0):
    # Find header
    header = None
    rowNum = 0  # 1 indexed row number

    for row in iterator:
        rowNum += 1
        if headerRowFirst is None or _cellValue(row[0]) == headerRowFirst:
            header = row
            break

    if header is None:
        raise Exception(f"header not found in CSV. headerRowFirst = `{headerRowFirst}`")

    keys = {}
    for i, k in enumerate(header):
        val = _cellValue(k)
        if isinstance(val, str):
            keys[val.strip()] = i

    for i in range(skipRows):
        rowNum += 1
        next(iterator)  # pylint: disable=stop-iteration-return # false positive

    # Iterate over rows
    rowObj = CSVRow(keys)
    for row in iterator:
        rowNum += 1

        # If all values are empty, we skip the row
        for c in row:
            v = _cellValue(c)
            if v is not None and v != '':
                break

        else:
            # Skip row
            continue

        if row:
            rowObj.row = row
            rowObj.rowNum = rowNum
            yield rowObj


def writeCSV(filenameOrFile, data, raw=False):
    """
    Write any data acceptable by pd.DataFrame(...) to CSV
    :param raw: If true, data bypasses dataframe, and instead a double array is expected
    """
    with openOrPassthrough(filenameOrFile, 'w') as f:
        if not raw:
            df = pd.DataFrame(data)
            data = [tuple(df.columns.values)] + [tuple(r) for rowI, r in df.iterrows()]

        writer = csv.writer(f)
        for l in data:
            writer.writerow(list(l))


def writeCSVFromRichTable(filenameOrFile, table):
    """
    Write any data from a Table for the rich library
    """
    with openOrPassthrough(filenameOrFile, 'w') as f:
        writer = csv.writer(f)

        # Header
        writer.writerow([c.header for c in table.columns])
        cols = [list(c.cells) for c in table.columns]

        for ri in range(len(table.rows)):
            writer.writerow([cd[ri] for cd in cols])


class CSVRow:
    """Helper class for reading csv files. Same object is reused"""

    def __init__(self, keys):
        self.keys = keys
        self.row = []
        self.rowNum = -1

    def tOpt(self, name, default=None, requireKey=False, cast=None):
        if name not in self.keys:
            if requireKey:
                raise Exception(f"Expected column {name} to exist")
            return default
        index = self.keys[name]
        cellValue = _cellValue(self.row[index])
        if not cellValue:
            return default

        return cast(cellValue) if cast is not None else cellValue

    def tVal(self, name, allowEmpty=False):
        if name not in self.keys:
            raise Exception(f"Expected column {name} to exist")
        val = _cellValue(self.row[self.keys[name]])
        if isinstance(val, str) and not val and not allowEmpty:
            raise Exception(f"Value expected for column {name} in row {self.rowNum}")
        return val

    def tOption(self, name, allowed: Iterable[Any], cast=None, requireKey=True):
        val = self.tOpt(name, '', requireKey=requireKey)
        if cast is not None:
            val = cast(val)
        if val not in allowed:
            raise Exception(f"Column {name} must have one of the following values: {allowed}. Found: {val}")
        return val

    def tOptionMap(self, name, allowed: dict[Any, Any], cast=None, requireKey=True):
        val = self.tOption(name, allowed.keys(), cast, requireKey)
        return allowed[val]

    def getDict(self):
        return {k: _cellValue(self.row[i]) for k, i in self.keys.items()}

    def __getitem__(self, k):
        return self.tVal(k, True)


def _cellValue(cell):
    # CSV reader has simple string values. XLS reader has Cell objects with a value method
    return cell if isinstance(cell, str) else cell.value
