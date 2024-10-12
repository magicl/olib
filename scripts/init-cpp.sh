#!/bin/bash
# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~

set -euo pipefail
trap "exit 1" ERR

sudo apt update
sudo apt install gcc
sudo apt install cmake
