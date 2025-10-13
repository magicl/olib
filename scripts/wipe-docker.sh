#!/bin/bash
# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~

#Delete all docker containers, images, volumes

if [ -n "$(docker container ls -aq)" ]; then
	docker container rm -f "$(docker container ls -aq)"
fi

if [ -n "$(docker image ls -aq)" ]; then
	docker image rm -f "$(docker image ls -aq)"
fi

if [ -n "$(docker volume ls -q)" ]; then \
	docker volume rm -f "$(docker volume ls -q)"
fi

docker builder prune -a -f
