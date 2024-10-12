# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~

import datetime

from django.test import tag
from django.utils import timezone

from olib.py.django.test.cases import OTestCase
from olib.py.utils.date import (
    defaultTimezone,
    genShopifyDateStr,
    parseShopifyDateStr,
    toLocalRemoveTz,
    toLocalTimezone,
    toUtcTimezone,
    utcDateFromStr,
    utcTimezone,
)


@tag('olib')
class Tests(OTestCase):

    def test_timezones(self):

        utcDt = utcDateFromStr('2019-01-10 12:00:00')

        self.assertEqual(utcDt.strftime('%Y-%m-%d %H:%M:%S %Z'), '2019-01-10 12:00:00 UTC')
        self.assertEqual(
            toLocalTimezone(utcDt).strftime('%Y-%m-%d %H:%M:%S %Z'),
            '2019-01-10 06:00:00 CST',
        )
        self.assertEqual(
            toLocalRemoveTz(toLocalTimezone(utcDt)).strftime('%Y-%m-%d %H:%M:%S %Z'),
            '2019-01-10 06:00:00 ',
        )
        self.assertEqual(
            toLocalRemoveTz(utcDt).strftime('%Y-%m-%d %H:%M:%S %Z'),
            '2019-01-10 06:00:00 ',
        )
        self.assertEqual(
            toUtcTimezone(toLocalRemoveTz(utcDt)).strftime('%Y-%m-%d %H:%M:%S %Z'),
            '2019-01-10 12:00:00 UTC',
        )
        self.assertEqual(
            utcTimezone(toLocalRemoveTz(utcDt)).strftime('%Y-%m-%d %H:%M:%S %Z'),
            '2019-01-10 06:00:00 UTC',
        )
        self.assertEqual(
            defaultTimezone(toLocalRemoveTz(utcDt)).strftime('%Y-%m-%d %H:%M:%S %Z'),
            '2019-01-10 06:00:00 CST',
        )

    def test_shopify_date_str(self):
        """Verifies parse and gen of shopify date strings"""

        now = timezone.now().replace(microsecond=0)
        self.assertEqual(parseShopifyDateStr(genShopifyDateStr(now)), now)

        self.assertEqual(
            parseShopifyDateStr('2012-08-24T14:01:47-04:00'),
            datetime.datetime(
                2012,
                8,
                24,
                14,
                1,
                47,
                0,
                tzinfo=datetime.timezone(datetime.timedelta(hours=-4)),
            ),
        )
