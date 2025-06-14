# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~

import io
from typing import Any

import pandas as pd
from django.test import tag

from olib.py.django.test.cases import OTestCase
from olib.py.utils.csv import readCSV, writeCSV
from olib.py.utils.xls import readXLS, writeXLS


@tag('olib')
class Tests(OTestCase):
    def test_csv_xls(self) -> None:
        """Verify CSV and XLS read and write"""

        # fcsv = './.output/test_utils_csv.csv'
        # fxls = './.output/test_utils_xls.xlsx'

        fcsv = io.StringIO()
        fxls = io.BytesIO()

        data = pd.DataFrame({'A': [1, 2, 3], 'B': ['x', 'y', 'z']})

        writeXLS(fxls, 'sheet', data)
        writeCSV(fcsv, data)

        fxls.seek(0)
        fcsv.seek(0)

        def read(itr: Any) -> list[tuple[Any, str]]:
            vals = []
            for r in itr:
                vals.append((r.tOpt('A', '?'), r.tVal('B')))
            return vals

        with readXLS(fxls) as xlsIter:
            self.assertEqual(read(xlsIter), [(1, 'x'), (2, 'y'), (3, 'z')])

        # CSV reader does not understand types, so everything is a string
        with readCSV(fcsv) as csvIter:
            self.assertEqual(read(csvIter), [('1', 'x'), ('2', 'y'), ('3', 'z')])
