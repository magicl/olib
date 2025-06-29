# Copyright (C) 2023 Øivind Loe - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# ~

"""
Type stubs for strawberry_django decorators to fix mypy errors.
"""

from collections.abc import Callable, Sequence
from typing import Any, Type, TypeVar, overload

from strawberry.extensions import FieldExtension

# Type variables for generic decorators
F = TypeVar('F', bound=Callable[..., Any])

# Common types used in decorators
ExtensionsType = Sequence[FieldExtension] | None
OnlyType = Sequence[str] | None
PrefetchRelatedType = Sequence[str] | None
SelectRelatedType = Sequence[str] | None
FieldNameType = str | None


# strawberry_django.field decorator
@overload
def field(
    *,
    extensions: ExtensionsType = None,
    only: OnlyType = None,
    prefetch_related: PrefetchRelatedType = None,
    select_related: SelectRelatedType = None,
    field_name: FieldNameType = None,
) -> Callable[[F], F]:
    ...

@overload
def field(func: F) -> F:
    ...


# strawberry_django.mutation decorator
@overload
def mutation(
    *,
    extensions: ExtensionsType = None,
) -> Callable[[F], F]:
    ...

@overload
def mutation(func: F) -> F:
    ...


# strawberry_django.connection decorator (for method decorators)
@overload
def connection(
    connection_type: Type[Any],
    *,
    extensions: ExtensionsType = None,
) -> Callable[[F], F]:
    ...

@overload
def connection(func: F) -> F:
    ...


# strawberry_django.connection function (for field assignments)
@overload
def connection() -> Any:
    ...

@overload
def connection(
    *,
    extensions: ExtensionsType = None,
) -> Any:
    ...


# strawberry_django.filters.apply function
def apply(
    filters: Any,
    queryset: Any,
    info: Any,
) -> Any:
    ...


# strawberry_django.django_resolver decorator
@overload
def django_resolver(
    *,
    qs_hook: Any = None,
) -> Callable[[F], F]:
    ...

@overload
def django_resolver(func: F) -> F:
    ...


# strawberry_django.mutations module
class mutations:
    @staticmethod
    def update(
        input_type: Type[Any],
        *,
        extensions: ExtensionsType = None,
    ) -> Any:
        ...

    @staticmethod
    def delete(
        input_type: Type[Any],
        *,
        extensions: ExtensionsType = None,
    ) -> Any:
        ...


# strawberry_django.relay module
class relay:
    class DjangoListConnection:
        ...


# strawberry_django.permissions module
class permissions:
    class IsAuthenticated(FieldExtension):
        ...

    class HasPerm(FieldExtension):
        def __init__(self, permission: str) -> None:
            ...

    class DjangoNoPermission(Exception):
        ...

    class DjangoPermissionExtension(FieldExtension):
        ...


# strawberry_django.utils.typing module
class utils:
    class typing:
        UserType = Any


# strawberry_django.filters module
class filters:
    @staticmethod
    def filter(model: Type[Any]) -> Callable[[Type[Any]], Type[Any]]:
        ...

    @staticmethod
    def apply(filters: Any, queryset: Any, info: Any) -> Any:
        ...


# strawberry_django.type, input, partial decorators (simplified)
def type(model: Type[Any], *, filters: Type[Any] | None = None) -> Callable[[Type[Any]], Type[Any]]:
    ...

def input(model: Type[Any]) -> Callable[[Type[Any]], Type[Any]]:
    ...

def partial(model: Type[Any]) -> Callable[[Type[Any]], Type[Any]]:
    ...
