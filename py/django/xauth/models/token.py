# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~

import base64
import os

from django.conf import settings
from django.db import models


class Token(models.Model):
    """Implements persistent login token, used to authenticate APIs"""

    TOKEN_LENGTH = 40

    key = models.CharField(max_length=TOKEN_LENGTH, primary_key=True)
    user = models.OneToOneField(settings.AUTH_USER_MODEL, related_name='auth_token', on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.key:
            self.key = Token.generate_key()

        return super().save(*args, **kwargs)

    @staticmethod
    def generate_key():
        return base64.b64encode(os.urandom(30), altchars=b'-_').decode()
