# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~

import strawberry
import strawberry_django
from strawberry_django.fields.types import OperationInfo
from strawberry_django.permissions import IsAuthenticated

from olib.py.django.xauth.authtoken import auth_token_delete, auth_token_get


@strawberry.type
class AuthTokenResponse:
    token: str


@strawberry.type
class Query:

    @strawberry.field
    async def auth_authenticated(self, info: strawberry.Info) -> bool:
        """Returns true if authenticated"""
        user = await info.context.request.auser()
        return not user.is_anonymous


@strawberry.type
class Mutation:

    @strawberry_django.mutation()
    def auth_token_get(self, username: str, password: str) -> AuthTokenResponse:
        """Create authorization token for the given user based on a provided password"""
        return AuthTokenResponse(token=auth_token_get(username, password))

    @strawberry_django.mutation(extensions=[IsAuthenticated()])
    def auth_token_delete(self, info: strawberry.Info) -> OperationInfo:
        """Delete auth token for the current user"""
        auth_token_delete(info.context.request.user)

        # Don't like the OperationInfo here.. Could use a custom mutation and return OperationInfo
        # if the mutation resturns None (or does not return anything)
        return OperationInfo(messages=[])
