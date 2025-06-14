# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~

import logging

from ..request import Requester, RequestError

logger = logging.getLogger(__name__)


class InfisicalApiError(Exception):
    pass


class Infisical(Requester):
    def __init__(self, client_id: str, client_secret: str, base_url: str = 'https://app.infisical.com') -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._access_token: str | None = None

        super().__init__(base_url=base_url, timeout=10)

    @property
    def access_token(self) -> str:
        if self._access_token is None:
            ret = super().request(
                'POST',
                '/api/v1/auth/universal-auth/login',
                data={
                    'clientSecret': self._client_secret,
                    'clientId': self._client_id,
                },
            )
            self._access_token = ret['accessToken']

        if self._access_token is None:
            raise InfisicalApiError('Failed to get access token')

        return self._access_token

    def request(
        self,
        method: str,
        url: str,
        data: dict | None = None,
        params: dict | None = None,
        headers: dict[str, str] | None = None,
        timeout: int | None = 10,
    ) -> dict:
        if headers is None:
            headers = {}

        headers['Authorization'] = f"Bearer {self.access_token}"

        return super().request(method, url, data, params, headers)

    def create_client_secret(self, identity_id: str, description: str) -> tuple[str, str]:
        """Will revoke any existing client secret with the identity_id and description, and then create a new one"""

        ret = self.request(
            'GET',
            f"/api/v1/auth/universal-auth/identities/{identity_id}/client-secrets",
        )

        for s in ret['clientSecretData']:
            if s['description'] == description:
                # Found one matching description.. Revoke it
                self.request(
                    'POST',
                    f"/api/v1/auth/universal-auth/identities/{identity_id}/client-secrets/{s['id']}/revoke",
                )
                break

        # Create a new client secret
        ret = self.request(
            'POST',
            f"/api/v1/auth/universal-auth/identities/{identity_id}/client-secrets",
            data={'description': description},
        )
        client_secret = ret['clientSecret']

        # Get clientId
        ret = self.request('GET', f"/api/v1/auth/universal-auth/identities/{identity_id}")
        client_id = ret['identityUniversalAuth']['clientId']

        return client_id, client_secret

    def read_secrets(
        self,
        project_slug: str,
        environment: str,
        secret_path: str = '/',
        recursive: bool = False,
        include_imports: bool = False,  # nosec: hardcoded_password_default
    ) -> dict[str, str]:
        try:
            ret = self.request(
                'GET',
                '/api/v3/secrets/raw',
                params={
                    'workspaceSlug': project_slug,
                    'environment': environment,
                    'secretPath': secret_path,
                    'recursive': 'true' if recursive else 'false',
                    'include_imports': 'true' if include_imports else 'false',
                },
            )
        except RequestError as e:
            logger.exception(e)
            return {}

        return {secret['secretKey']: secret['secretValue'] for secret in ret['secrets']}
