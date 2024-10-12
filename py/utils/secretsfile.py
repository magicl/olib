# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~

"""
Maintains a local file of secrets, each with a visible key and a value that is encrypted with a local key, or a key managed by a key service
"""

import os
from base64 import b64decode, b64encode

from .encrypt import aesDecrypt, aesEncrypt
from .secrets import LocalSharedFileSecret, SecretProvider


class SecretsFile:
    EXPECTED_FILE_MODE = 0o600

    def __init__(
        self,
        file_path: str,
        secret_provider: SecretProvider | None = None,
        separator='||',
    ):
        self.file_path = os.path.expanduser(file_path)
        self.secret_provider = secret_provider if secret_provider is not None else LocalSharedFileSecret()
        self.separator = separator

        # Verify correct privileges
        if os.path.exists(self.file_path):
            mode = os.stat(self.file_path).st_mode & 0xFFF
            if mode != self.EXPECTED_FILE_MODE:
                raise Exception(
                    f"Secrets file exists, but does not have correct permissions ({mode:o}) != ({self.EXPECTED_FILE_MODE:o}), so will not be used"
                )

    def _token_map_read(self):
        if os.path.exists(self.file_path):
            try:
                token_map = {}
                with open(self.file_path, encoding='utf-8') as f:
                    # Each line consists of key:value, where value is an encrypted, then base64-encoded string.
                    for line in f:
                        split = line.strip().split(self.separator)
                        if len(split) != 2:
                            print(f"Ignoring malformed line in secrets file: {split}")
                            continue

                        token_map[split[0]] = split[1]

                return token_map
            except Exception as e:
                raise Exception('unable to read token file') from e

        return {}

    def _token_map_write(self, token_map):
        # Create dir and file
        os.makedirs(os.path.dirname(self.file_path), mode=self.EXPECTED_FILE_MODE, exist_ok=True)
        if os.path.dirname(self.file_path).rsplit('/', 1)[1] not in (
            'tmp',
            '.output',
        ):  # nosec: hardcoded_tmp_directory
            os.chmod(self.file_path, mode=self.EXPECTED_FILE_MODE)  # Just in case it was already made with wrong privs

        # Write tokens
        with open(self.file_path, 'w', encoding='utf-8') as f:
            for key, entry in token_map.items():
                f.write(f"{key}{self.separator}{entry}\n")

        os.chmod(self.file_path, mode=self.EXPECTED_FILE_MODE)

        # Verify correct privileges
        mode = os.stat(self.file_path).st_mode & 0xFFF
        if mode != self.EXPECTED_FILE_MODE:
            raise Exception(
                f"Token file created, but with wrong mode. Actual vs expected: {mode:o} vs {self.EXPECTED_FILE_MODE:o}"
            )

    def get_secret(self, key):
        """Returns None if secret is not present"""
        token_map = self._token_map_read()

        if key not in token_map:
            return None

        return aesDecrypt(b64decode(token_map[key]), self.secret_provider.get_secret(), signed=False).decode('utf-8')

    def save_secret(self, key, data):
        token_map = self._token_map_read()

        token_map[key] = b64encode(aesEncrypt(data, self.secret_provider.get_secret(), sign=False)).decode('utf-8')

        self._token_map_write(token_map)

    def delete_secret(self, key):
        """
        Delete secret
        :returns: False if secret was not present
        """

        # Read existing tokens if present
        token_map = self._token_map_read()
        present = key in token_map

        if present:
            del token_map[key]
            self._token_map_write(token_map)

        return present

    def list_keys(self):
        token_map = self._token_map_read()
        return list(token_map.keys())

    def clear_secrets(self):
        self._token_map_write({})
