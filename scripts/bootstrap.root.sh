#!/bin/bash
# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~


# Base packages
apt-get update && apt-get -y install \
    curl \
    build-essential \
    libffi-dev \
    libgdbm-dev \
    libncurses5-dev \
    libnss3-dev \
    libreadline-dev \
    libsqlite3-dev \
    libssl-dev \
    default-libmysqlclient-dev \
    wget \
    zlib1g-dev \
    pkg-config \
    libbz2-dev \
    tk-dev \
    liblzma-dev \
	clang
