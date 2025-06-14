# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~
import json
from typing import Any

from googleapiclient.discovery import build
from oauth2client.service_account import ServiceAccountCredentials


def gdGetService(creds: str) -> Any:
    # Auth example: https://developers.google.com/drive/api/quickstart/python
    scopes = ['https://www.googleapis.com/auth/drive']

    credentials = ServiceAccountCredentials.from_json_keyfile_dict(json.loads(creds), scopes=scopes)

    return build('drive', 'v3', credentials=credentials)


def gdListFiles(
    service: Any, driveId: str, query: str | None = None, fields: tuple[str, ...] = ('id', 'name')
) -> list[dict[str, Any]]:
    files = []
    pageToken = None

    while True:
        ret = (
            service.files()
            .list(
                q=query,
                driveId=driveId,
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
                corpora='drive',
                pageSize=1000,
                fields=f"nextPageToken, files({','.join(fields)})",
                pageToken=pageToken,
            )
            .execute()
        )

        files += ret['files']

        if 'nextPageToken' in ret:
            pageToken = ret['nextPageToken']
        else:
            break

    return files
