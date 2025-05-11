# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~

from typing import Any


class Config:
    displayName = 'APP'
    insts: list[dict[str, Any]] | None = None
    tools = ['python']
    license = 'restrictive'
