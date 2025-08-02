# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~

import logging

from django.test import tag

from olib.py.django.test.cases import OTestCase
from olib.py.utils.logexpect import ExpectLogItem, expectLogItems

logger = logging.getLogger(__name__)


@tag('olib')
class Tests(OTestCase):
    def test_inline_decorator(self) -> None:
        with expectLogItems([ExpectLogItem('olib.py.tests.utils.test_logexpect', logging.ERROR, r'.*test.*')]):
            logger.error('test')

    @expectLogItems([ExpectLogItem('olib.py.tests.utils.test_logexpect', logging.ERROR, r'.*test.*')])
    def test_function_decorator(self) -> None:
        logger.error('test')
