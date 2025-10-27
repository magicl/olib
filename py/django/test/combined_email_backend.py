# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~
"""
Email backend that writes messages to console instead of sending them.
"""


from collections.abc import Sequence
from typing import Any

from django.core.mail.backends.base import BaseEmailBackend
from django.core.mail.backends.console import EmailBackend as ConsoleEmailBackend
from django.core.mail.backends.filebased import EmailBackend as FileBasedEmailBackend
from django.core.mail.message import EmailMessage


class CombinedEmailBackend(BaseEmailBackend):
    """Email backend that writes messages to console and files. This makes it very useful
    for when when running the backend in a docker container and testingn it with playwright."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

        self.file_backend = FileBasedEmailBackend(*args, **kwargs)
        self.console_backend = ConsoleEmailBackend(*args, **kwargs)

    def send_messages(self, email_messages: Sequence[EmailMessage]) -> int:
        """Write all messages to the stream in a thread-safe way."""
        self.console_backend.send_messages(email_messages)
        self.file_backend.send_messages(email_messages)

        return len(email_messages)
