# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~

import logging
from typing import TYPE_CHECKING

from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.backends import ModelBackend

from olib.py.django.xauth.models.token import Token
from olib.py.exceptions import UserError

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from django.contrib.auth.models import User  # pylint: disable=imported-auth-user
else:
    User = get_user_model()


def auth_token_get(username: str, password: str, request=None):
    if not (username and password):
        raise UserError('Both username and password must be provided to create a token')

    user = authenticate(request=request, username=username, password=password)

    token, _ = Token.objects.get_or_create(user=user)

    return token.key


def auth_token_delete(user: User):
    token = Token.objects.get(user=user)
    token.delete()


class AuthTokenBackend(ModelBackend):
    """
    Authentication backend for processing token-based authorization. The token is passed in the X-Access-Token
    NOTE: Still requires the user to log in, but the login can be done using the token
    """

    def authenticate(self, request, username=None, password=None, **kwargs) -> User | None:
        if request is None:
            return None

        token = request.headers.get('X-Access-Token', None)

        if token is None:
            logger.debug('Request missing access token header')
            return None

        if len(token) < Token.TOKEN_LENGTH:
            logger.error(f"Token length only {len(token)}")
            return None

        return User.objects.filter(auth_token__key=token).first()
