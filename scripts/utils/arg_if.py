#!/usr/bin/env python3
# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~
# Helper for argument checking in scripts. Checks if an argumet is part of an arguments string
# Inputs:
# $1: argument to check for
# $2: List of input arguments to check in

# isort: off
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parents[1]))
# isort: on

if sys.argv[1] in sys.argv[2]:
    sys.exit(0)
else:
    sys.exit(1)
