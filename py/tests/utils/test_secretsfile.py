# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~

import os

from django.test import tag

from olib.py.django.test.cases import OTestCase
from olib.py.utils.secretsfile import SecretsFile


@tag('olib')
class Tests(OTestCase):

    def test_basic(self):
        path = './.output/test_utils_secretsfile.txt'
        if os.path.exists(path):
            os.remove(path)

        f = SecretsFile(path)

        self.assertIsNone(f.get_secret('a'))
        self.assertEqual(f.list_keys(), [])

        f.save_secret('a', 'hello')
        f.save_secret('b', 'you')
        self.assertEqual(f.get_secret('a'), 'hello')
        self.assertEqual(f.get_secret('b'), 'you')
        self.assertEqual(f.list_keys(), ['a', 'b'])

        f.delete_secret('b')
        self.assertIsNone(f.get_secret('b'))
        self.assertEqual(f.list_keys(), ['a'])

        f.clear_secrets()
        self.assertEqual(f.list_keys(), [])
