# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~

import json
import time
from typing import Any, NamedTuple

from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Max, QuerySet, Subquery

from olib.py.django.conf.models import OnlineSetting
from olib.py.exceptions import UserError
from olib.py.utils.execenv import isEnvProduction, isEnvTest


class OnlineSettingDef(NamedTuple):
    name: str
    type: str
    default: Any
    cache_timeout_seconds: int
    values: list[Any] | None
    load_group: str | None


class CachedValue(NamedTuple):
    value: Any
    timeout: float


_settingDefs: dict[str, OnlineSettingDef] = {}


class OnlineSettingRef:
    def __init__(self, name: str) -> None:
        if name not in osettings.settings:
            raise ObjectDoesNotExist(f"Online setting does not exist: {name}")

        self.name = name

    def val(self) -> Any:
        return getattr(osettings, self.name)

    def __int__(self) -> int:
        if osettings.settings[self.name].type != 'int':
            raise Exception(f"Online setting {self.name} is not an int")

        return getattr(osettings, self.name)  # type: ignore[no-any-return]

    def __float__(self) -> float:
        if osettings.settings[self.name].type != 'float':
            raise Exception(f"Online setting {self.name} is not a float")

        return getattr(osettings, self.name)  # type: ignore[no-any-return]

    def __str__(self) -> str:
        if osettings.settings[self.name].type != 'str':
            raise Exception(f"Online setting {self.name} is not a str")

        return getattr(osettings, self.name)  # type: ignore[no-any-return]

    def __bool__(self) -> bool:
        if osettings.settings[self.name].type != 'bool':
            raise Exception(f"Online setting {self.name} is not a bool")

        return getattr(osettings, self.name)  # type: ignore[no-any-return]


class OnlineSettingsAccess:
    """Provides cache and easy lookup of settings"""

    MAX_STR_LEN = 32000

    _list_types = ('list-str', 'list-float', 'list-int', 'list-bool')
    _key_types = ('key-str', 'key-float', 'key-int', 'key-bool')

    def __init__(self) -> None:
        self._cache: dict[str, CachedValue] = {}
        self.settings = _settingDefs  # Member to allow easy access and mocking

    def __getattr__(self, name: str) -> Any:
        cached_val = self._cache.get(name)
        t = time.time()

        if cached_val is None or cached_val.timeout < t:
            spec = self.settings[name]

            # Settings value not in cache, or timed out. Read setting or settings group if a group has been specified
            self._read(name, spec.load_group)

            cached_val = self._cache[name]

        return cached_val.value

    def __setattr__(self, name: str, value: Any) -> None:
        if name in ('_cache', 'settings'):
            super().__setattr__(name, value)
        else:
            raise Exception('Online settings should not be modified like this. Use OnlineSetting.write')

    def invalidate(self) -> None:
        if not isEnvTest():
            raise Exception(
                'Online settings cache invalidation can only be done in testcases, as the invalidation would be local only to the current node'
            )
        self._cache = {}

    def _read(self, name: str | None = None, load_group: str | None = None) -> None:
        """Read option for a name or for given group. Makes sense to read group at the same time, because options from the same group are often used temporally close"""

        if load_group is not None:
            names = tuple(k for k, v in self.settings.items() if v.load_group == load_group)
        else:
            names = (name,) if name else ()

        last_ids = Subquery(
            OnlineSetting.objects.filter(name__in=names).values('name').annotate(lastId=Max('id')).values('lastId')
        )
        val_objs = {v.name: v for v in OnlineSetting.objects.filter(id__in=last_ids)}

        t = time.time()

        for n in names:
            spec = self.settings[n]
            val_obj = val_objs.get(n)

            if val_obj is None:
                val = spec.default
            else:
                val = OnlineSettingsAccess.cast(val_obj.name, val_obj.value)

            # Write to cache
            self._cache[n] = CachedValue(val, t + spec.cache_timeout_seconds)

    def ref(self, name: str) -> OnlineSettingRef:
        """Online setting ref. Use as placeholder for online setting"""
        return OnlineSettingRef(name)

    def register(
        self,
        name: str,
        type: str,
        default: Any,
        values: list[Any] | None = None,
        load_group: str | None = None,
        cache_timeout_seconds: int | None = None,
    ) -> None:
        if name in self.settings:
            raise Exception(f"Setting {name} already defined")

        if cache_timeout_seconds is None:
            cache_timeout_seconds = 5 * 60 if isEnvProduction() else 10

        self.settings[name] = OnlineSettingDef(name, type, default, cache_timeout_seconds, values, load_group)

    @staticmethod
    def cast(name: str, v: Any) -> Any:
        # Cast
        cast_to = osettings.settings[name].type
        val: Any

        if cast_to == 'int':
            val = int(v)
        elif cast_to == 'float':
            val = float(v)
        elif cast_to == 'str':
            val = v
        elif cast_to == 'bool':
            val = v == '1'
        elif cast_to in OnlineSettingsAccess._list_types:
            val = json.loads(v) if v else []
        elif cast_to in OnlineSettingsAccess._key_types:
            val = json.loads(v) if v else {}
        else:
            raise Exception(f"Unknown type for onlinesetting {name}: {cast_to}")

        return val

    @staticmethod
    def cast_input_str(name: str, v: str) -> tuple[str, str]:
        if len(v) > OnlineSettingsAccess.MAX_STR_LEN:
            raise UserError(
                f"String length of setting must be no more than {OnlineSettingsAccess.MAX_STR_LEN} for: {name}"
            )
        return v, v

    @staticmethod
    def cast_input_bool(name: str, v: Any) -> tuple[str, bool]:
        if isinstance(v, bool):
            return ('1' if v else '0'), v

        lower = v.lower()
        if lower in ('0', 'f', 'false', 'off'):
            return '0', False
        if lower in ('1', 't', 'true', 'on'):
            return '1', True

        raise UserError(f"{v} is not a valid bool. Use one of t/true/on/1 or f/false/off/0")

    @staticmethod
    def cast_input_int(name: str, v: Any) -> tuple[str, int]:
        if isinstance(v, int):
            return str(v), v

        if isinstance(v, str):
            try:
                return v, int(v)
            except ValueError:
                pass

        raise UserError(f"{v} is not a valid int. An int is required for: {name}")

    @staticmethod
    def cast_input_float(name: str, v: Any) -> tuple[str, float]:
        if isinstance(v, (float, int)):
            return str(v), v

        if isinstance(v, str):
            try:
                return v, float(v)
            except ValueError:
                pass

        raise UserError(f"{v} is not a valid float. A float is required for: {name}")

    @staticmethod
    def cast_input(name: str, value: Any, prefix: str | None = None) -> tuple[str, Any]:

        spec = OnlineSettingsAccess._get_spec(name)
        cast_val: Any

        type = spec.type
        if prefix is not None:
            if not type.startswith(prefix):
                raise UserError(f"Operation cannot be done on type {type}")

            # Remove prefix so sub-value can be validated
            type = type[len(prefix) :]

        if type == 'str':
            value, cast_val = OnlineSettingsAccess.cast_input_str(name, value)

        elif type == 'bool':
            value, cast_val = OnlineSettingsAccess.cast_input_bool(name, value)

        elif type == 'int':
            value, cast_val = OnlineSettingsAccess.cast_input_int(name, value)

        elif type == 'float':
            value, cast_val = OnlineSettingsAccess.cast_input_float(name, value)

        elif type in OnlineSettingsAccess._list_types:
            sub_check = _sub_checks[type]
            if isinstance(value, list):
                cast_val = [sub_check(name, v)[1] for v in value]
                value = json.dumps(cast_val)

            else:
                raise Exception(f"{type} can only be written directly with a List")

        elif type in OnlineSettingsAccess._key_types:
            sub_check = _sub_checks[type]
            if isinstance(value, dict) and all(isinstance(k, str) for k, _ in value.items()):
                cast_val = {k: sub_check(name, v)[1] for k, v in value.items()}
                value = json.dumps(cast_val)

            else:
                raise Exception(f"{type} can only be written directly with a Dict")

        else:
            raise UserError(f"Cannot use 'write' command on data of type {spec.type}")

        if spec.values is not None:
            values = spec.values
            if callable(values):
                values = values()
            if cast_val not in values:
                raise UserError(f"For onlinesetting {name}, one of the following values are required: {spec.values}")

        return value, cast_val

    @staticmethod
    def _get_spec(name: str) -> OnlineSettingDef:

        # Validate
        if name not in osettings.settings:
            raise ObjectDoesNotExist(f"Online setting does not exist: {name}")

        return osettings.settings[name]

    @staticmethod
    def write(name: str, value: Any, *, invalidateCache: bool = False, forceUpdate: bool = False) -> OnlineSetting:
        """
        Update a setting
        :param invalidateCache: Use in testcases only to invalidate cache
        :param forceUpdate: Update even if value did not change
        """

        value, cast_val = OnlineSettingsAccess.cast_input(name, value)
        ret = None

        if not forceUpdate and cast_val == getattr(osettings, name):
            # No write is necessary, however if no value object exists, and we are using the default value, we'll create a value anyway
            ret = OnlineSetting.objects.filter(name=name).order_by('id').last()

        if ret is None:
            # Create / update
            ret = OnlineSetting.objects.create(
                name=name,
                value=value,
            )

            if invalidateCache:
                osettings.invalidate()

        return ret

    @staticmethod
    def set(name: str, key: str, value: Any, *, invalidateCache: bool = False) -> OnlineSetting:
        """
        Add a key/value to a setting
        :param invalidateCache: Use in testcases only to invalidate cache
        """

        spec = OnlineSettingsAccess._get_spec(name)

        if spec.type not in OnlineSettingsAccess._key_types:
            raise UserError('Cannot set a key for this setting')

        _, cast_val = OnlineSettingsAccess.cast_input(name, value, prefix='key-')

        # Fetch last version of setting so it can be modified
        last_val = OnlineSetting.objects.filter(name=name).order_by('-id').first()
        if last_val is None:
            dict_val = spec.default
        else:
            dict_val = json.loads(last_val.value)

        dict_val[key] = cast_val

        # Should be all good. Write it. Create a new value so we can track changes
        ret = OnlineSetting.objects.create(
            name=name,
            value=json.dumps(dict_val),
        )

        if invalidateCache:
            osettings.invalidate()

        return ret

    @staticmethod
    def add(name: str, value: str, *, invalidateCache: bool = False) -> OnlineSetting:
        """
        Add a value to a setting
        :param invalidateCache: Use in testcases only to invalidate cache
        """

        spec = OnlineSettingsAccess._get_spec(name)

        if spec.type not in OnlineSettingsAccess._list_types:
            raise UserError('Cannot add an item for this setting')

        _, cast_val = OnlineSettingsAccess.cast_input(name, value, prefix='list-')

        # Fetch last version of setting so it can be modified
        last_val = OnlineSetting.objects.filter(name=name).order_by('-id').first()
        if last_val is None:
            list_val = spec.default
        else:
            list_val = json.loads(last_val.value)

        if cast_val in list_val:
            raise UserError('Setting already contains value')

        list_val.append(cast_val)

        # Should be all good. Write it. Create a new value so we can track changes
        ret = OnlineSetting.objects.create(
            name=name,
            value=json.dumps(list_val),
        )

        if invalidateCache:
            osettings.invalidate()

        return ret

    @staticmethod
    def clr(name: str, key: str, *, invalidateCache: bool = False) -> OnlineSetting:
        """
        Remove a key
        :param invalidateCache: Use in testcases only to invalidate cache
        """

        spec = OnlineSettingsAccess._get_spec(name)

        if spec.type not in OnlineSettingsAccess._key_types and spec.type not in OnlineSettingsAccess._list_types:
            raise UserError('Cannot remove an item from this setting')

        # Fetch last version of setting so it can be modified
        last_val = OnlineSetting.objects.filter(name=name).order_by('-id').first()
        if last_val is None:
            val = spec.default
        else:
            val = json.loads(last_val.value)

        if key not in val:
            raise UserError(f"Key {key} does not exist in {name}")

        if isinstance(val, dict):
            del val[key]
        elif isinstance(val, list):
            val.remove(key)
        else:
            raise Exception('unexpected type: {type(val)}')

        # Should be all good. Write it. Create a new value so we can track changes
        ret = OnlineSetting.objects.create(
            name=name,
            value=json.dumps(val),
        )

        if invalidateCache:
            osettings.invalidate()

        return ret

    @staticmethod
    def get_latest_query() -> QuerySet[OnlineSetting]:
        """
        Returns a query fetching the latest settings. Note that some settings might not be present if
        they have not yet been written. Default value must in that case be retried from the SETTINGS struct
        """

        return OnlineSetting.objects.filter(
            id__in=Subquery(OnlineSetting.objects.values('name').annotate(maxId=Max('id')).values('maxId'))
        )


_sub_checks = {
    'list-str': OnlineSettingsAccess.cast_input_str,
    'list-int': OnlineSettingsAccess.cast_input_int,
    'list-float': OnlineSettingsAccess.cast_input_float,
    'list-bool': OnlineSettingsAccess.cast_input_bool,
    'key-str': OnlineSettingsAccess.cast_input_str,
    'key-int': OnlineSettingsAccess.cast_input_int,
    'key-float': OnlineSettingsAccess.cast_input_float,
    'key-bool': OnlineSettingsAccess.cast_input_bool,
}


osettings = OnlineSettingsAccess()
