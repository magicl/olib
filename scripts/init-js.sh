#!/bin/bash
# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~

set -euo pipefail
trap "exit 1" ERR

LOCAL_DIR=$(dirname "$(realpath "$0")")

if [ ! -e $HOME/.nvm ]; then
	. $LOCAL_DIR/bootstrap.js.sh
fi

# Install packages in current dir and child dirs that have a package.json
for dir in . */ ; do
    # Check if package.json exists in the directory
    if [ -f "$dir/package.json" ]; then
        echo "Running 'npm ci' in $dir"
        (cd "$dir" && npm ci)
    fi
done
