#!/bin/bash
# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~

#Install python support.
#Args:
#  $1 - Mode: uv or pyenv
#  $2 - Optionally install requirements.txt file passed in as second argument

set -euo pipefail
trap "exit 1" ERR

PYTHON_VERSION=3.13.3

LOCAL_DIR=$(dirname "$(realpath "$0")")
MODE=${1:-}
REQUIREMENTS=${2:-}

if [[ "$MODE" != "pyenv" && "$MODE" != "uv" ]]; then
	>&2 echo "ERROR: bootstrap.py.sh requires specifying uv or pyenv as fist param"
	exit 1
fi

#Sudo is not available in containers. In those, the root commands
#are execued separately
if type sudo >/dev/null 2>&1; then
	sudo $LOCAL_DIR/bootstrap.root.sh
fi

if [[ "$MODE" == "pyenv" ]]; then
	# Install pyenv
	command -v pyenv || curl https://pyenv.run | bash
else
	# Install uv
	curl -LsSf https://astral.sh/uv/install.sh | sh
fi

#Init env
. $LOCAL_DIR/bootstrap.env.sh

if [[ "$MODE" == "pyenv" ]]; then
	#Install target python version
	pyenv install -s $PYTHON_VERSION
fi

#Install requirements file if passed in
if [[ -n $REQUIREMENTS ]]; then
	if [[ "$MODE" == "pyenv" ]]; then
		pyenv local $PYTHON_VERSION
		pip install -r $REQUIREMENTS
	else
		uv venv --python $PYTHON_VERSION
		uv pip install -r $REQUIREMENTS
	fi
fi
