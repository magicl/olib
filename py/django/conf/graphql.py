# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~

from collections.abc import Coroutine, Iterable
from typing import Any

import strawberry
import strawberry_django
from strawberry import relay
from strawberry_django.permissions import HasPerm

from .osettings import (  # type: ignore[attr-defined]
    OnlineSetting,
    OnlineSettingsAccess,
    osettings,
)


async def _read_online_settings(node_ids: Iterable[str] | None = None) -> list['OnlineSettingType']:
    # Fetch data from db
    query = OnlineSettingsAccess.get_latest_query()
    if node_ids is not None:
        query = query.filter(name__in=node_ids)

    db_settings = {os.name: os async for os in query}

    # Pass down in-order, either object or (k, v) tuple of spec
    # return [{'name': k, 'value': db_settings.get(k), 'type': v.type} for k, v in osettings.settings.items()]
    # return [OnlineSetting(relay_id=k, name=k, value=db_settings.get(k), type=v.type) for k, v in osettings.settings.items()]
    return [OnlineSettingType.make(k, db_settings.get(k)) for k, _ in osettings.settings.items()]


@strawberry.type
class OnlineSettingType(relay.Node):
    relay_id: relay.NodeID[str]
    name: str
    value: str | None
    type: str

    @classmethod
    def resolve_nodes(
        cls, *, info: strawberry.Info, node_ids: Iterable[str], required: bool = False
    ) -> Coroutine[Any, Any, list['OnlineSettingType']]:
        return _read_online_settings(node_ids)

    @staticmethod
    def make(name: str, obj: 'OnlineSetting' | None) -> 'OnlineSettingType':
        os_def = osettings.settings[name]
        return OnlineSettingType(
            relay_id=name,
            name=name,
            value=obj.value if obj is not None else None,
            type=os_def.type,
        )


@strawberry.type
class Query:

    @relay.connection(  # type: ignore[misc]
        relay.ListConnection[OnlineSettingType],
        extensions=[HasPerm('conf.view_onlinesetting')],
    )
    async def online_settings(self) -> list[OnlineSettingType]:
        return await _read_online_settings()


@strawberry.type
class Mutation:

    @strawberry_django.mutation(extensions=[HasPerm('conf.change_onlinesetting')])  # type: ignore[misc]
    def online_setting_update(self, name: str, value: str) -> OnlineSettingType:
        """Update online setting"""
        # NOTE: Make sure to control what comes out in OperationInfo on production to not leak sensitive error data (!).. Might want to implement
        #       this myself... ..
        #       OperationInfo: https://github.com/strawberry-graphql/strawberry-django/blob/main/strawberry_django/fields/types.py#L202
        #       OperationMessage: https://github.com/strawberry-graphql/strawberry-django/blob/main/strawberry_django/fields/types.py#L159
        #       Could do by patching: https://github.com/strawberry-graphql/strawberry-django/blob/main/strawberry_django/mutations/fields.py#L43
        obj = osettings.write(name, value)
        return OnlineSettingType.make(name, obj)

    @strawberry_django.mutation(extensions=[HasPerm('conf.change_onlinesetting')])  # type: ignore[misc]
    def online_setting_add_key(self, name: str, value: str) -> OnlineSettingType:
        """Add item to online setting"""
        obj = osettings.add(name, value)
        return OnlineSettingType.make(name, obj)

    @strawberry_django.mutation(extensions=[HasPerm('conf.change_onlinesetting')])  # type: ignore[misc]
    def online_setting_set_key(self, name: str, key: str, value: str) -> OnlineSettingType:
        """Add key/value pair to online setting"""
        obj = osettings.set(name, key, value)
        return OnlineSettingType.make(name, obj)

    @strawberry_django.mutation(extensions=[HasPerm('conf.change_onlinesetting')])  # type: ignore[misc]
    def online_setting_remove_key(self, name: str, key: str) -> OnlineSettingType:
        """Remove key or value from online setting"""
        obj = osettings.clr(name, key)
        return OnlineSettingType.make(name, obj)
