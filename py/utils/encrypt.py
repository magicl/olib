# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~

import base64
import hashlib
import hmac
import os
from hashlib import pbkdf2_hmac

from Crypto import (
    Random,  # nosec(B413:blacklist) # Incorrectly detected as pyCrypto, but we are using pycryptodome
)
from Crypto.Cipher import (
    AES,  # nosec(B413:blacklist) # Incorrectly detected as pyCrypto, but we are using pycryptodome
)


def sha256hex(pt, normalize=True):
    """Returns hexdigest of a sha256 function on a string. Matches google and facebook requirements for hashing emails, etc..."""
    if normalize:
        pt = pt.strip().lower()
    return hashlib.sha256(pt.encode()).hexdigest()


def sha512Signature(bdata, key, returnHex=False):
    key = key.encode('utf-8') if isinstance(key, str) else key
    calc = hmac.new(key, bdata, hashlib.sha512)
    return calc.hexdigest() if returnHex else calc.digest()


def sha1Signature(bdata, key):
    key = key.encode('utf-8') if isinstance(key, str) else key
    return hmac.new(key, bdata, hashlib.sha1).digest()


def aesEncrypt(plaintext: str | bytes, key: str | bytes, sign=True) -> bytes:
    """
    :param key: if string, base64 is assumed
    """
    iv = Random.new().read(AES.block_size)
    key = base64.b64decode(key) if isinstance(key, str) else key
    plaintext = plaintext.encode('utf-8') if isinstance(plaintext, str) else plaintext

    cipher = AES.new(key, AES.MODE_CFB, iv)
    msg = iv + cipher.encrypt(plaintext)

    if sign:
        # Use sha1 truncated from 64 bytes to 20 to keep link short and sweet
        msg += sha1Signature(msg, key)[:20]

    return msg


def aesDecrypt(ciphertext: bytes, key: str | bytes, signed=True) -> bytes:
    """
    :param key: if string, base64 is assumed
    """
    key = base64.b64decode(key) if isinstance(key, str) else key

    if signed:
        # Check and strip signature
        signature = sha1Signature(ciphertext[:-20], key)
        if signature[:20] != ciphertext[-20:]:
            raise Exception('Signature validation failed')
        ciphertext = ciphertext[:-20]

    iv = Random.new().read(AES.block_size)
    cipher = AES.new(key, AES.MODE_CFB, iv)

    return cipher.decrypt(ciphertext)[len(iv) :]


def hmacEncode(data: bytes, secret: str, algo=hashlib.sha256, b64=True):
    hash_ = hmac.new(secret.encode('utf-8'), data, algo)

    if b64:
        return str(base64.b64encode(hash_.digest()), 'utf-8')
    return hash_.hexdigest()


def hmacIsValid(data: bytes, hmacExp: str, secret: str, algo=hashlib.sha256, b64=True):
    return hmacEncode(data, secret, algo, b64=b64) == hmacExp


def keygen(password: str | bytes | None = None, key_length=32, iter=500000) -> bytes:
    """Create a key based on the password, or get a random key if no password is present"""
    if password is None:
        return os.urandom(key_length)

    if isinstance(password, str):
        password = password.encode('utf-8')

    salt = os.urandom(16)  # Store this salt safely

    # Derive the key
    key = pbkdf2_hmac(
        hash_name='sha256',
        password=password,
        salt=salt,
        iterations=iter,
        dklen=key_length,
    )

    return key
