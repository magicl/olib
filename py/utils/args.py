# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~

import re
import sys
from typing import Any


def testArg(options: dict[str, Any], keep=False):
    """
    Checks for special arg, and deletes it to avoid errors from manage.py
    :param keep: Set to not remove param from sys.argv. By default it is removed
    """
    for opt, val in options.items():
        reg = re.compile(opt)
        for v in sys.argv:
            m = reg.match(v)
            if m:
                if not keep:
                    sys.argv.remove(v)

                if callable(val):
                    return val(m)

                return val

    return False
