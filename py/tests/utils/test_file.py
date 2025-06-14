# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~


from django.test import tag

from olib.py.django.test.cases import OTestCase
from olib.py.utils.file import acceptableFilename


@tag('olib')
class Tests(OTestCase):
    def test_acceptable_filename(self) -> None:
        self.assertEqual(acceptableFilename('F[ x!_foo-bar!?'), 'f-x_foo-bar')
