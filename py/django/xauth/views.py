# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.db.models import Q
from django.shortcuts import render

from .authorization import assumeUserAdminLoggedIn, checkAccess, viewAccess

User = get_user_model()


@viewAccess('xauth__view_admins')
def admins(request):
    permissions = getattr(settings, 'XAUTH_PERMISSIONS')

    users = list(User.objects.filter(Q(is_superuser=True) | Q(is_staff=True)).all())
    groups = list(Group.objects.all())

    # Permissions and groups in sets by users
    groupSets = {du.id: {g.name for g in du.groups.all()} for du in users}
    groupPermSets = {dg.id: {d.codename for d in dg.permissions.all()} for dg in groups}

    context = {
        'users': users,
        'groups': groups,
        'permissions': list(Permission.objects.all()),
        'groupSets': groupSets,
        'groupPermSets': groupPermSets,
        'perms': permissions,
        'checkAccess': checkAccess,
    }

    with assumeUserAdminLoggedIn(users):
        return render(request, 'xauth/admins.html', context, using='jinja2')
