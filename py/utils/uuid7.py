# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~

from typing import cast
from uuid import UUID

import uuid_extensions


def uuid7() -> UUID:
    """For some reason, db migrations don't like using uuid_extensions directly as default value. This wrapper helps"""
    return cast(UUID, uuid_extensions.uuid7())
