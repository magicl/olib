# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~

import secrets
import string


def makePassword(length=32, symbols=False):
    """Make a safe pwd that is easily copyable, i.e. avoid - and other characters that could break selection when double-clicking the pwd in a shell"""
    if symbols:
        characters = string.ascii_letters + string.digits + string.punctuation
    else:
        characters = string.ascii_letters + string.digits + '.'

    return ''.join(secrets.choice(characters) for i in range(length))
