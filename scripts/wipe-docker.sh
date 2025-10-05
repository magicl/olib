#!/bin/bash

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
