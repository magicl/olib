# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~


from django.db import models


class Asset(models.Model):
    """
    Asset base. Any content is stored in AssetContent, even if the asset is a link. Asset base provides a connection point for versioning of content
    """

    created_at = models.DateTimeField(auto_now_add=True, blank=True, null=True)

    namespace = models.CharField(max_length=10, db_default='', db_comment='App name responsible for asset')
    key = models.CharField(max_length=10, db_default='', db_comment='Must be unique within namespace')
    content = models.ForeignKey(
        'models.AssetContent',
        on_delete=models.CASCADE,
        db_comment='Link to content. Always valid',
    )

    class Meta:
        unique_together = [('namespace', 'key')]


class AssetContent(models.Model):
    """
    A version of asset content
    """

    created_at = models.DateTimeField(auto_now_add=True, blank=True, null=True)
    asset = models.ForeignKey(Asset, null=True, on_delete=models.SET_NULL)

    created_at = models.DateTimeField(auto_now_add=True, blank=True, null=True)
    created_by = models.ForeignKey('User', on_delete=models.CASCADE, null=True)
    updated_at = models.DateTimeField(auto_now_add=True, blank=True, null=True)

    usage = models.IntegerField(db_default=0, db_comment='Number of times asset has been used in production')
