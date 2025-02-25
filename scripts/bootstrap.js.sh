#!/bin/bash
# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~

set -euo pipefail
trap "exit 1" ERR

LOCAL_DIR=$(dirname "$(realpath "$0")")

# Install / update NVM, the node.js version manager
export PROFILE=/dev/null #Tell nvm installer to not update .zshrc / .bashrc
wget -qO- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash

# Init NVM
. $LOCAL_DIR/bootstrap.env.sh

# For now, just install latest LTS
# Update: --lts = v22 had some issues on Jenkins
nvm install 20 #--lts
nvm use 20 #--lts

nvm install-latest-npm

# Faster npm alternative
npm install --global corepack@latest
corepack enable pnpm
