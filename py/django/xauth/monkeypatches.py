# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~

# Specifically targeting User model, so pylint: disable=imported-auth-user
from django.contrib.auth.models import User as BaseUser

# pylint: enable=imported-auth-user


def applyMonkeyPatches():
    # Add _ownership field to base User model. In case of User model override, overrider is responsible for providing _ownership
    # Intentionall setting protected member, so pylint: disable=protected-access
    BaseUser._ownership = (
        'id',
        'user',
    )
    # pylint: enable=protected-access
