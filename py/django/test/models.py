# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~

# Only used for olib test, so
# pylint: disable=imported-auth-user
from django.contrib.auth.models import User

# pylint: enable=imported-auth-user
from django.db import models


class TestXAuthOwnedModel(models.Model):
    value = models.CharField(max_length=100)
    owner = models.ForeignKey(User, null=True, on_delete=models.SET_NULL)
    staff_only = models.BooleanField(default=True)

    _ownership = ('owner_id', 'user')


class TestXAuthParentModel(models.Model):
    owned = models.ForeignKey(TestXAuthOwnedModel, null=True, on_delete=models.SET_NULL)

    _ownership = ('owned__owner_id', 'user')
