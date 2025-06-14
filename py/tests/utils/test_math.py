# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~

import logging
from typing import Any

import numpy as np
from django.test import tag

from olib.py.django.test.cases import OTestCase
from olib.py.utils.math import percentile, percentilePrep

logger = logging.getLogger(__name__)


@tag('olib')
class Tests(OTestCase):

    def test_percentile(self) -> None:
        """Verifies percentile calculation based on datasets"""

        np.testing.assert_almost_equal(percentilePrep([1, 2, 3, 4], 5), [1, 2, 3, 4])  # Lower number.. Simply returned
        np.testing.assert_almost_equal(percentilePrep([1, 2, 3, 4], 2), [1, 3, 4])
        np.testing.assert_almost_equal(percentilePrep([1, 2, 3, 4], 3), [1, 2, 4])

        def check(values: Any, expPercentiles: Any, dataSet: Any, targetSegments: Any) -> None:
            prep = percentilePrep(dataSet, targetSegments)
            pvals = [percentile(value, prep) for value in values]
            np.testing.assert_almost_equal(pvals, expPercentiles)

        check(
            [0, 1, 1.5, 2, 2.5, 3, 3.5, 4, 4.5, 5, 5.5],
            [1, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100],
            [1, 2, 3, 4, 5],
            5,
        )
        check(
            [0, 1, 1.5, 2, 2.5, 3, 3.5, 4, 4.5, 5, 5.5],
            [1, 13, 25, 25, 25, 38, 50, 62, 75, 87, 100],
            [1, 2, 3, 4, 5],
            3,
        )
        check(
            [0, 1, 1.5, 2, 2.5, 3, 3.5, 4, 4.5, 5, 5.5],
            [1, 17, 34, 34, 34, 50, 67, 67, 67, 83, 100],
            [1, 2, 3, 4, 5],
            2,
        )
