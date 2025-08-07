# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~


"""Async helpers for testing"""

from typing import Any

from asgiref.sync import sync_to_async


async def sync_breakpoint(data: Any) -> None:
    """Provides a sync breakpoint for async code to make it easier to interact e.g. with models"""

    def sync_code(data: Any) -> None:
        print('--------------------------------')
        breakpoint()  # pylint: disable=forgotten-debug-statement
        pass  # pylint: disable=unnecessary-pass

    await sync_to_async(sync_code)(data)
