#!/bin/bash
# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~

#Install autoenv to automatically execute .env files to set
#correct env vars and aliases per project

set -euo pipefail
trap "exit 1" ERR

AUTOENV_DIR=~/.autoenv

if [[ ! -e $AUTOENV_DIR ]]; then
	#https to avoid dependency on ssh having been set up
	git clone https://github.com/hyperupcall/autoenv.git ~/.autoenv
fi

pushd $AUTOENV_DIR > /dev/null
git pull
popd > /dev/null

SCRIPT='source ~/.autoenv/activate.sh'
for rc in ~/.bashrc ~/.zshrc; do
	if ! grep "$SCRIPT" $rc > /dev/null; then
		echo "Adding autoenv to $rc"
		echo "$SCRIPT" >> $rc
	fi
done
