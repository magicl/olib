#!/bin/bash
# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~

set -euo pipefail
shopt -s nullglob #prevent glob from expanding to glob itself when no files are found
trap "exit 1" ERR

PYTHON_VERSION=3.12.6
CUR_DIR=${PWD##*/}
VENV_NAME=$CUR_DIR
#VENV_PATH=~/.pyenv/versions/${VENV_NAME}
VENV_PATH=$CUR_DIR/.pyenv
dev='true'
force='false'
havegit='true'

showHelp() {
    echo "Usage: $0 [options]"
    echo ""
    echo "Options:"
    echo "  --dev [true/false]  Set or clear dev mode"
    echo "  --nodev             Disable dev mode, i.e. not enabling pre-commit"
    echo "  --help              Display this help message and exit."
    echo "  --force             Allow init also in directories without a .git folder"
    echo ""
}

# Parse command line arguments
while [[ "$#" -gt 0 ]]; do
    case $1 in
        --dev) dev="$2"; shift ;;
        --nodev) dev='false' ;;
        --force) force='true' ;;
        --help) showHelp  ; exit 1 ;;
        -h) showHelp ; exit 1 ;;
        *) echo "Unknown parameter: $1"; exit 1 ;;
    esac
    shift
done

if [[ ! -e .git ]] ; then
    if [[ "$force" = false ]]; then
        echo "Please call 'init' from the root directory in a project, i.e. the one containing the '.git' folder"
        exit 1
    fi
    havegit='false'
fi

if [[ $CUR_DIR != "olib" ]]; then
    #Initializing olib-using project
    #Ensure project has access to .env
    if [[ ! -e .envrc ]]; then
        ln -sf olib/.envrc .envrc
    fi
    if [[ ! -e .envrc.leave ]]; then
        ln -sf olib/.envrc.leave .envrc.leave
    fi
fi

#Load env vars
source .envrc

requirementsPath="."
if [ -e backend/requirements.txt ]; then
    requirementsPath="backend"
fi

pyRequirements=""
for f in $requirementsPath/requirements*.txt; do
    pyRequirements+="-r $f "
done

if [[ $CUR_DIR != "olib" ]]; then
    #if [[ ! -e .gitignore ]]; then
    #GIT does not allow symlink for .gitignore
    cp -f olib/.gitignore .gitignore
    #fi
    if [[ ! -e .pre-commit-config.yaml ]]; then
        ln -sf olib/.pre-commit-config.yaml .pre-commit-config.yaml
    fi

    pyRequirements+="-r $OLIB_PATH/requirements_dev.txt"
fi


if [[ "$force" = true ]]; then
    #Delete directories, triggering full refresh
    echo "Deleting all existing pip/npm packages..."
    #pyenv virtualenv-delete -f "$VENV_NAME" || true
    #rm -rf ./node_modules
    #npmArgs=" --force"
	rm -rf $VENV_PATH
fi


if [ ! -d $VENV_PATH ] || ! pip -V; then
    #Just in case
    #pyenv update
    #pyenv install -s $PYTHON_VERSION

    #Create new environment
    echo "Creating new virtualenv $VENV_NAME for `whoami`"
    rm -rf $VENV_PATH
    #pyenv virtualenv $PYTHON_VERSION $VENV_NAME
    #pyenv local $VENV_NAME
	uv venv --python $PYTHON_VERSION --prompt $VENV_NAME $VENV_PATH
fi

if [ "$(uname)" == "Darwin" ]; then
    # shellcheck disable=SC1090
    #source "/Users/$USER/.pyenv/versions/${VENV_NAME}/bin/activate"
	. $VENV_PATH/bin/activate
else
    # shellcheck disable=SC1090
    #source "/home/$USER/.pyenv/versions/${VENV_NAME}/bin/activate"
	. $VENV_PATH/bin/activate
fi

#Setup remaining stuff
#pip install wheel setuptools pip ipdb parproc -U
#pip install $pyRequirements -U
pip install uv
uv pip install $pyRequirements

#Ensure pre-commit is installed (git hooks)
if [[ "$dev" == true && "$havegit" == true ]]; then
    pre-commit install
    pre-commit autoupdate
fi
