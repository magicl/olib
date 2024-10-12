#!/bin/bash
# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~

#Init pyenv
if [ -e $HOME/.pyenv ]; then
	echo "Initializing pyenv"
	export PATH="$HOME/.pyenv/bin:$PATH"
	eval "$(pyenv init --path)"
	eval "$(pyenv virtualenv-init -)"
fi

#UV (pip / pyenv alternative)
if [ -d $HOME/.cargo ]; then
	. "$HOME/.cargo/env"
fi


#Init nvm (optionally present)
if [ -e $HOME/.nvm ]; then
	echo "Initializing nvm"
	export NVM_DIR="$HOME/.nvm"
	[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"
fi
