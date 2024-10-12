# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~


import uuid


def createUser(username=None, permissions=None, **kwargs):
    from django.contrib.auth import get_user_model
    from django.contrib.auth.models import Permission

    User = get_user_model()

    if username is None:
        username = f"user-{uuid.uuid4()}"

    if 'email' not in kwargs:
        kwargs = {**kwargs, 'email': username}

    user = User.objects.create_user(username, **kwargs)

    if permissions:
        permissionObjs = list(Permission.objects.filter(codename__in=permissions).all())
        user.user_permissions.add(*permissionObjs)

        if missingPermissions := set(permissions) - {p.codename for p in permissionObjs}:
            raise Exception(f"Did not recognize permissions: {missingPermissions}")

        # Flush permissions. NOTE: Is this really necessary?
        if hasattr(user, '_perm_cache'):
            delattr(user, '_perm_cache')

    return user


def resetCaches():
    # Implement system where application can register a function to reset caches
    pass
