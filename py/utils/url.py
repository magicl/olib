# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~

from urllib.parse import parse_qs


def split_url(url: str) -> tuple[str, dict[str, str]]:
    """Split URL into path and map of get params"""
    idx = url.find('?')
    if idx >= 0:
        path = url[:idx]
        parsed = parse_qs(url[idx + 1 :], keep_blank_values=True)
        # For some reason, every value is wrapped in array index
        getvars = {k: v[0] for k, v in parsed.items()}
    else:
        path = url
        getvars = {}

    return path, getvars
