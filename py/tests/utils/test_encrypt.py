# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~

from django.test import tag

from olib.py.django.test.cases import OTestCase
from olib.py.utils.encrypt import aesDecrypt, aesEncrypt, keygen


@tag('olib')
class Tests(OTestCase):
    def test_aes(self):
        plaintext = b'Some text to encrypt'

        key0 = keygen('Key0', iter=1)
        key1 = keygen('Key1', iter=1)

        # Encrypt
        ciphertext0 = aesEncrypt(plaintext, key0)
        ciphertext1 = aesEncrypt(plaintext, key1)

        self.assertNotEqual(ciphertext0, ciphertext1)
        self.assertNotEqual(ciphertext0, plaintext)
        self.assertNotEqual(ciphertext1, plaintext)

        # Decrypt
        result0 = aesDecrypt(ciphertext0, key0)
        result1 = aesDecrypt(ciphertext1, key1)

        self.assertEqual(result0, plaintext)
        self.assertEqual(result1, plaintext)

        # Verify signing.. Should not be possible to get half the text back by cutting the input in half
        with self.assertRaises(Exception):
            aesDecrypt(ciphertext0[:10], key0)
