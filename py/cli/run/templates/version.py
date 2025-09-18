# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~


from typing import Any

from olib.infra.services.version import VersionManager

from .base import prep_config


def version() -> Any:
    """
    Make version object available to context. The version object must be
    initialized as part of the build process
    """

    def decorator(cls: Any) -> Any:
        prep_config(cls)
        cls.meta.version = VersionManager()
        return cls

    return decorator
