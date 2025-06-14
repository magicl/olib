# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~

import json
import logging
from functools import reduce
from typing import Any

import gspread
from gspread.exceptions import APIError
from gspread_dataframe import get_as_dataframe, set_with_dataframe
from gspread_formatting import border  # pylint: disable=no-name-in-module
from gspread_formatting import borders  # pylint: disable=no-name-in-module
from gspread_formatting import cellFormat  # pylint: disable=no-name-in-module
from gspread_formatting import color  # pylint: disable=no-name-in-module
from gspread_formatting import numberFormat  # pylint: disable=no-name-in-module
from gspread_formatting import textFormat  # pylint: disable=no-name-in-module
from gspread_formatting import batch_updater, format_cell_range
from oauth2client.service_account import ServiceAccountCredentials

from ...throttle import exponentialBackoff

logger = logging.getLogger(__name__)

# IMPORTANT: TO ALLOW ACCESS
# - Make sure to share sheet with the service account user email


# Backoff for gspread functions:
def expBackoff(func):
    return exponentialBackoff(
        func,
        lambda e: isinstance(e, APIError)
        and any(
            v in str(e)
            for v in [
                'Quota exceeded',
                'The Service is currently unavailable',
                'The server encountered a temporary error',
            ]
        ),
        maxRetries=8,
        initialDelaySeconds=10,
        maxDelaySeconds=60,
    )


def colFromInt(n: int) -> str:
    """Returns column name from a column index"""
    string = ''
    while n > 0:
        n, remainder = divmod(n - 1, 26)
        string = chr(65 + remainder) + string
    return string


def sheetCoord(col: int, row: int) -> str:
    colStr = colFromInt(col)
    return f"{colStr}{row}"


def getSheet(sheet, key, url, gs, creds):
    if isinstance(sheet, str):
        return (gsOpen(creds, key=key, url=url) if gs is None else gs).worksheet(sheet)

    return sheet


def gsOpen(creds: str | None, key: str | None = None, url: str | None = None) -> Any:
    if creds is None:
        raise Exception('must provide JSON credentials object')

    scopes = [
        'https://spreadsheets.google.com/feeds',
        'https://www.googleapis.com/auth/drive',
    ]
    credentials = ServiceAccountCredentials.from_json_keyfile_dict(json.loads(creds), scopes=scopes)
    gc = gspread.authorize(credentials)

    if key is not None:
        gc = expBackoff(lambda: gc.open_by_key(key))
    elif url is not None:
        gc = expBackoff(lambda: gc.open_by_url(url))
    else:
        raise Exception('Key or URL must be defined')

    return gc


def gsReadDataFrame(sheet, key=None, url=None, gs=None, creds=None, skipRows=None):
    sheet = getSheet(sheet, key, url, gs, creds)
    return expBackoff(lambda: get_as_dataframe(sheet, evaluate_formulas=True, skiprows=skipRows))


def gsWriteDataFrame(
    df,
    sheet,
    key=None,
    url=None,
    gs=None,
    creds=None,
    clear=True,
    row=1,
    col=1,
    header=None,
):
    sheet = getSheet(sheet, key, url, gs, creds)
    if clear:
        # https://docs.gspread.org/en/v4.0.0/
        expBackoff(sheet.clear)

    if header is not None:
        # Write content header
        expBackoff(lambda: sheet.update(range_name=sheetCoord(col, row), values=[[header]]))
        row += 1

    expBackoff(lambda: set_with_dataframe(sheet, df, resize=False, row=row, col=col))


def gsUpdateFormatted(
    values,
    sheet,
    key=None,
    url=None,
    gs=None,
    creds=None,
    clear=True,
    clearFormat=True,
    row=1,
    col=1,
    header=None,
):
    """
    :param values: 2-dimensional list where values can be tuples if they want styles applied to them. The styles for a given cell will be combined. Styles should be'
                   specified using 'CellFormat' as seen here: https://github.com/robin900/gspread-formatting?tab=readme-ov-file
    """
    sheet = getSheet(sheet, key, url, gs, creds)
    if clear:
        expBackoff(sheet.clear)

    # Write data to sheet
    data = [[v[0] if isinstance(v, tuple) else v for v in row] for row in values]
    expBackoff(lambda: sheet.update(sheetCoord(1, 1), data))

    if clearFormat:
        expBackoff(
            lambda: format_cell_range(
                sheet,
                f"A1:{sheetCoord(sheet.col_count, sheet.row_count)}",
                cellFormat(
                    backgroundColor=color(1, 1, 1),
                    textFormat=textFormat(bold=False, foregroundColor=color(0, 0, 0)),
                    numberFormat=numberFormat(type='TEXT', pattern=''),
                    # horizontalAlignment=None,
                    # verticalAlignment=None,
                    borders=borders(
                        top=border(style='NONE'),
                        bottom=border(style='NONE'),
                        left=border(style='NONE'),
                        right=border(style='NONE'),
                    ),
                ),
            )
        )

    # Apply styles
    def applyStyles() -> None:
        with batch_updater(sheet.spreadsheet) as batch:
            for ri, row_ in enumerate(values):
                for ci, val in enumerate(row_):
                    if isinstance(val, tuple) and len(val) > 1:
                        aggFmt = reduce(lambda a, b: a + b, val[1:])
                        batch.format_cell_range(  # pylint: disable=no-member
                            sheet, sheetCoord(col + ci, row + ri), aggFmt
                        )  # pylint: disable=no-member

    expBackoff(applyStyles)


def addGroupsOffset(groups: list[dict[str, int]], offset: int) -> list[dict[str, int]]:
    for g in groups:
        g['start'] += offset
        g['end'] += offset

    return groups


def _gsApplyGroups(groups, listGroups, deleteGroup, addGroup):
    # Check if current grouping matches spec. In that case, nothing to do
    exiGroups = {(g['range']['startIndex'], g['range']['endIndex'], g['depth']) for g in listGroups()}
    newGroups = {(g['start'], g['end'], g['depth']) for g in groups}

    if exiGroups == newGroups:
        return

    # Clear all groups so we can rebuild
    for start, end, _ in exiGroups:
        expBackoff(lambda: deleteGroup(start, end))  # pylint: disable=cell-var-from-loop

    # Rebuild, starting with innermost groups
    for g in sorted(groups, key=lambda g: -g['depth']):
        expBackoff(lambda: addGroup(g['start'], g['end']))  # pylint: disable=cell-var-from-loop


def gsApplyRowGroups(sheet: Any, groups: list[dict[str, int]]) -> None:
    """
    Groups should have format
    [{'start': NN, 'end': NN, depth: NN}]

    Depth = 1 is higest up. Depth = 2 would e.g. be nested inside a range of depth 1
    """
    _gsApplyGroups(
        groups,
        sheet.list_dimension_group_rows,
        sheet.delete_dimension_group_rows,
        sheet.add_dimension_group_rows,
    )


def gsApplyColGroups(sheet: Any, groups: list[dict[str, int]]) -> None:
    _gsApplyGroups(
        groups,
        sheet.list_dimension_group_columns,
        sheet.delete_dimension_group_columns,
        sheet.add_dimension_group_columns,
    )
