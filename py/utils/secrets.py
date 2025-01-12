# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~

import base64
import os
import re
from abc import ABC, abstractmethod
from getpass import getpass

from .encrypt import keygen


class SecretMissingError(Exception):
    pass


class SecretFilePermissionsError(Exception):
    pass


def readFileSecretSplit(filename) -> list[str]:
    value = readFileSecret(filename)
    return [v.strip() for v in re.split('\n| ', value)]


def readFileSecret(filename) -> str:
    filename = os.path.expanduser(filename)
    filename = os.path.expandvars(filename)

    if os.path.exists(filename):
        # Verify file permissions set correctly, to ensure other users of computer cannot access
        stat = os.stat(filename).st_mode

        expStat = 0o100400
        if stat != expStat:
            raise SecretFilePermissionsError(
                f"Secret file {filename} does not have correct permissions. Has {oct(stat)}, please change to {oct(expStat)}"
            )

        # Read file
        with open(filename, encoding='utf-8') as f:
            return f.read().strip()

    raise SecretMissingError(f"Secret file {filename} is missing")


class SecretProvider(ABC):
    """Allows access to a secret without keeping the secret in memory for the duration of a program"""

    @abstractmethod
    def get_secret(self): ...


class ConstSecret(SecretProvider):
    def __init__(self, const: bytes):
        self.const = const

    def get_secret(self):
        return self.const


class FileSecret(SecretProvider):
    def __init__(self, filename):
        self.filename = filename

    def get_secret(self):
        return readFileSecret(self.filename)


class LocalSharedFileSecret(FileSecret):
    """A local file secret. Created if not present"""

    PATH = '~/.infrabase/secrets/localshared'

    def __init__(self):
        super().__init__(os.path.expanduser(self.PATH))

        if not os.path.exists(self.filename):
            os.makedirs(os.path.dirname(self.filename), exist_ok=True)

            with open(self.filename, 'w', encoding='utf-8') as f:
                f.write(base64.b64encode(keygen()).decode('utf-8'))

            os.chmod(self.filename, 0o400)


class PasswordInputSecret(ConstSecret):
    """Prompts for password on creation, then derives a key from password"""

    def __init__(self, prompt: str):
        key = keygen(getpass(prompt))
        super().__init__(key)
