# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~

"""Provides primitives for simplifying interaction with external APIs"""

import json
import logging
from typing import Any

import requests

logger = logging.getLogger(__name__)


class RequestError(Exception):
    pass


def base_request(
    method: str,
    base_url: str,
    url: str,
    data: dict[str, Any] | None = None,
    params: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 10,
    session: Any = None,
) -> dict[str, Any]:
    if params is None:
        params = {}

    full_url = f"{base_url}{url}"
    if params:
        full_url = full_url + '?' + '&'.join(k + '=' + str(v) for k, v in params.items())

    if session is None:
        session = requests  # Run without session

    again = True
    while again:
        again = False
        try:
            if method == 'GET':
                r = session.get(full_url, json=data, headers=headers, timeout=timeout)
            elif method == 'POST':
                r = session.post(full_url, json=data, headers=headers, timeout=timeout)
            elif method == 'PUT':
                r = session.put(full_url, json=data, headers=headers, timeout=timeout)
            elif method == 'DELETE':
                r = session.delete(full_url, json=data, headers=headers, timeout=timeout)
            elif method == 'PATCH':
                r = session.patch(full_url, json=data, headers=headers, timeout=timeout)
            else:
                raise Exception(f"Unsupported method: {method}")

            logger.info(f"call {method} {full_url} response {r.status_code} in {r.elapsed.total_seconds()}")

        except Exception as e:
            msg = f"Invalid response during {method} {full_url} - exception: {str(e)}"
            logger.error(msg)
            raise RequestError(msg) from e

        if r.status_code < 200 or r.status_code >= 300:
            try:
                errJson = r.json()
                msg = f"error result {r.status_code} from {method} {full_url}\nSENT:{data}\nRECEIVED:{errJson}"
            except json.JSONDecodeError:
                errJson = {}
                msg = f"error result {r.status_code} from {method} {full_url}\nSENT:{data}\nRECEIVED <unable to parse>:{r.text}"

            # NOTE: To add more customization, create an error handler interface that can be passed into the base request
            #      so error customization can be injected
            #      RETRY: Also do this for retry management.. Can provide general pre-made handlers as well.. I.e. a list of handlers can
            #      be provided

            raise RequestError(msg)

    try:
        jsonResp: dict[str, Any] = r.json()
    except Exception as e:
        msg = f"Unable to parse\nURL:'{full_url}'\nJSON:'{r.text}'"
        logger.error(msg)
        raise RequestError(msg) from e

    return jsonResp


class Requester:
    def __init__(self, base_url: str, session: Any = None, timeout: int = 10, retry: bool = True) -> None:
        self.base_url = base_url
        self.session = session if session is not None else requests.Session()
        self.timeout = timeout

    def request(
        self,
        method: str,
        url: str,
        data: Any = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeout: int | None = None,
    ) -> dict[str, Any]:
        if timeout is None:
            timeout = self.timeout

        return base_request(method, self.base_url, url, data, params, headers, timeout, self.session)
