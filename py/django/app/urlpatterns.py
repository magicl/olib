# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~
from django.conf import settings
from django.core.files.storage import default_storage
from django.http import FileResponse, Http404
from django.urls import re_path
from django.views.static import serve

from olib.py.utils.execenv import isEnvTest


def serve_inmemory_file(request, path):
    try:
        file = default_storage.open(path)
        return FileResponse(file)
    except FileNotFoundError as e:
        raise Http404(f"File not found: {path}") from e


def debug_file_urlpatterns():
    if not (settings.DEBUG or isEnvTest()):
        raise Exception('Only include these in DEBUG or TEST mode')

    using_inmemory_storage = settings.DEFAULT_FILE_STORAGE == 'django.core.files.storage.InMemoryStorage'

    serve_media: list = (
        [serve_inmemory_file] if using_inmemory_storage else [serve, {'document_root': settings.MEDIA_ROOT}]
    )
    serve_static: list = [serve, {'document_root': settings.STATIC_ROOT}]

    return [
        re_path(fr'^{settings.MEDIA_URL.strip('/')}\/(?P<path>.*)$', *serve_media),
        re_path(fr'^{settings.STATIC_URL.strip('/')}\/(?P<path>.*)$', *serve_static),
    ]
