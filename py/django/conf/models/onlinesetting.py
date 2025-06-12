# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~

"""
Settings that can be updated at runtime without re-deployment or restart

Usage:

x = osettings.x

will fetch property x from the database if a cached version is not available

For placeholders in code, use osettings.ref('X')


"""

from django.db import models


class OnlineSetting(models.Model):
    """Settings that can updated at runtime. Keeps old values to allow us to see history of settings changes"""

    name = models.CharField(max_length=191)
    value = models.TextField()

    created_at = models.DateTimeField(auto_now_add=True)  # When new value was set
    # created_by = models.ForeignKey(User, on_delete=models.CASCADE) #Who set the value

    # _priv_fields = None

    class Meta:
        indexes = [models.Index(fields=['name', 'created_at'])]

        default_permissions = ('view', 'change')

        # permissions = (
        #    ('view_onlinesetting', 'View onlinesettings'),
        #    ('change_onlinesetting', 'Change onlinesettings'),
        # )
