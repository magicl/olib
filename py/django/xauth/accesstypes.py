# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~

from django.contrib.auth.models import AnonymousUser


class UnknownLoggedInUser(AnonymousUser):  # pylint: disable=abstract-method
    """
    Only passes 'client' test, i.e. logged in, but not connected to any personal data. Used to pre-render data for logged in, but at that
    point unknown users
    """
