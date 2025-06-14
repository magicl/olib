# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~
import json
from typing import Any

# from compressor.contrib.jinja2ext import CompressorExtension
from django.contrib.staticfiles.storage import staticfiles_storage
from django.urls import reverse
from django.utils.timezone import localtime
from jinja2 import Environment

from olib.py.utils.execenv import isEnvLocal


# Escape string to make it ok to place in "". MUST use "", not '' around string
def strEscape(inp: Any) -> Any:
    # json.dumps includes quotes. The slicing is to remove them
    return json.dumps(inp)[1:-1]


def environment(**options: Any) -> Any:
    env = Environment(
        trim_blocks=True,
        lstrip_blocks=True,
        autoescape=True,
        auto_reload=isEnvLocal(),
        **{k: v for k, v in options.items() if k not in {'autoescape', 'auto_reload'}},
    )
    env.globals.update(
        {
            'static': staticfiles_storage.url,
            #'localstatic': localstatic_storage.url,
            'url': reverse,
            'localtime': localtime,
        }
    )

    env.filters.update(
        {
            'strEscape': strEscape,
            'localtime': localtime,
            'min': min,
            'max': max,
            'str': str,
        }
    )

    return env
