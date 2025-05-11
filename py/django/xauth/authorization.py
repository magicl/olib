# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~

import logging
from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from contextlib import contextmanager
from functools import wraps
from typing import TYPE_CHECKING, Any, Callable, Generator, Sequence
from urllib.parse import urlparse

from django.conf import settings
from django.contrib.auth import REDIRECT_FIELD_NAME, get_user_model
from django.contrib.auth.models import AnonymousUser
from django.contrib.auth.views import redirect_to_login
from django.db.models import Model, QuerySet
from django.http import HttpRequest, HttpResponse
from django.shortcuts import resolve_url

from .exceptions import PermissionConfigurationException, PermissionException
from .primitives import objectAccessAttributes  # pylint: disable=unused-import
from .primitives import (
    AccessAnd,
    AccessBase,
    _getAccAndUser,
    _objectAccessAnnotate,
    _objectAccessFilter,
)

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    # Only used for type checking, so
    # pylint: disable=imported-auth-user
    from django.contrib.auth.models import User

    # pylint: enable=imported-auth-user
else:
    User = get_user_model()


def redirectToLogin(request, login_url: str | None = None, redirect_field_name=None) -> HttpResponse:
    """Returns response to redirect to login for authentication, with a redirect back to current page"""
    login_url = login_url or 'admin:login'
    redirect_field_name = redirect_field_name or REDIRECT_FIELD_NAME

    path = request.build_absolute_uri()
    resolved_login_url = resolve_url(login_url or settings.LOGIN_URL)
    # If the login url is the same scheme and net location then just
    # use the path as the "next" url.
    login_scheme, login_netloc = urlparse(resolved_login_url)[:2]
    current_scheme, current_netloc = urlparse(path)[:2]
    if (not login_scheme or login_scheme == current_scheme) and (not login_netloc or login_netloc == current_netloc):
        path = request.get_full_path()

    return redirect_to_login(path, resolved_login_url, redirect_field_name)


def checkAccExists(accessName: str) -> bool:
    permissions = getattr(settings, 'XAUTH_PERMISSIONS')
    return permissions.get(accessName) is not None


def checkAccess(
    accessName: str,
    user: User | AnonymousUser | None = None,
    request: HttpRequest | None = None,
    viewName: str = '',
    returnBool: bool = False,
    simpleMessage: bool = False,
) -> bool:
    """Checks for blanket (non-object-based) access to a given resource"""
    acc, user = _getAccAndUser(accessName, user=user, request=request)

    # Process permissions
    if not acc.checkUser(user, request=request):
        ident = userIdentStr(user)
        if simpleMessage:
            msg = f"Permission denied for {ident} at view {viewName or accessName}"
        else:
            msg = f"Permission denied for {ident} at view {viewName or accessName}. Requires {filteredReason(acc, user, request=request)}"
        if returnBool:
            logger.info(msg)
            return False
        raise PermissionException(msg)

    if not acc.isPrivilegeCheck():  # NOTE: As optimization this can be run for all access-methods at startup!
        raise PermissionConfigurationException(f"Privilege check not done for view {viewName or accessName}")

    return True


@contextmanager
def checkAccesses(
    user: User | AnonymousUser | None = None,
    request: HttpRequest | None = None,
    returnBool: bool = True,
) -> Generator[Callable[[str | Sequence[str]], bool], None, None]:
    """Context manager returning a function that can be used for cached validation of access for a single entity, useful if a large number of individual permissions need to be checked"""
    accessResult: dict[str, bool] = {}

    def check(accessNameOrNames: str | Sequence[str]):
        accessNames: Sequence[str]

        if isinstance(accessNameOrNames, str):
            accessNames = (accessNameOrNames,)
        else:
            accessNames = accessNameOrNames

        for accessName in accessNames:
            res = accessResult.get(accessName, None)
            if res is None:
                res = checkAccess(accessName, user, request, returnBool=returnBool)
                accessResult[accessName] = res

            if not res:
                return False

        return True

    yield check


@contextmanager
def assumeAdminLoggedIn(users: Iterable[User]) -> None:
    """Marks user as logged in. Use in cases where it is desirable to check whether a user would have access if logged in. Will clear status after end of section"""
    oldBackends = [getattr(u, 'backend', 'NONE') for u in users]
    for u in users:
        setattr(u, 'backend', 'django.contrib.auth.backends.ModelBackend')

    yield

    # Restore
    for u, oldBe in zip(users, oldBackends):
        if oldBe == 'NONE':
            delattr(u, 'backend')
        else:
            setattr(u, 'backend', oldBe)


@contextmanager
def assumeUserAdminLoggedIn(users: Iterable[User]) -> None:
    """Marks user as logged in. Use in cases where it is desirable to check whether a user would have access if logged in. Will clear status after end of section"""
    oldBackends = [getattr(u, 'backend', 'NONE') for u in users]
    for u in users:
        setattr(u, 'backend', 'django.contrib.auth.backends.ModelBackend')

    yield

    # Restore
    for u, oldBe in zip(users, oldBackends):
        if oldBe == 'NONE':
            delattr(u, 'backend')
        else:
            setattr(u, 'backend', oldBe)


def applyObjectAccessFilter(
    querySet: QuerySet,
    accessName: str,
    model: Model,
    user: User | AnonymousUser | None = None,
    request: HttpRequest | None = None,
    viewName: str = '',
    returnBool: bool = False,
) -> QuerySet:
    qFilter, qAnnotate = objectAccessFilter(
        accessName,
        model,
        user=user,
        request=request,
        viewName=viewName,
        returnBool=returnBool,
    )
    return querySet.filter(qFilter).annotate(**qAnnotate)


def objectAccessFilter(accessName: str, model: Model, user: User | AnonymousUser | None = None, request: HttpRequest | None = None, viewName: str = '', returnBool: bool = False) -> tuple[QuerySet, dict[str, Any]]:
    """Only checks for object-specific access. 'checkAccess' must also be run to ensure user-specific access is checked. Returns both filter
    and necessary annotations"""
    acc, user = _getAccAndUser(accessName, user=user, request=request)
    if not acc:  # At least one permission MUST be present. Empty permissions are not acceptable
        return False  # _getAccAndUser throws for us if returnBool=False

    # Build permissions filter
    return _objectAccessFilter(acc, user, model, request), _objectAccessAnnotate(acc, model)


def objectAccessAnnotate(accessName: str, model: Model, user: User | AnonymousUser | None = None, request: HttpRequest | None = None, viewName: str = '', returnBool: bool = False) -> dict[str, Any]:
    acc, user = _getAccAndUser(accessName, user=user, request=request)
    if not acc:  # At least one permission MUST be present. Empty permissions are not acceptable
        return False  # _getAccAndUser throws for us if returnBool=False

    return _objectAccessAnnotate(acc, model)


def filteredReason(
    accObj: 'AccessBase',
    user: User | AnonymousUser | None,
    obj: object | None = None,
    model: Model | None = None,
    request: HttpRequest | None = None,
) -> str:
    """Use this for reason messages to ensure that internal details don't leak"""
    reason = accObj.reason(user, obj, model, request=request)

    # logger.info('ERR ON PRODUCTION ACCESS: {}'.format(checkAccess('_gql__errorMessagesOnProduction', user=user, request=request, returnBool=True, simpleMessage=True)))
    if not checkAccess(
        '_gql__errorMessagesOnProduction',
        user=user,
        request=request,
        returnBool=True,
        simpleMessage=True,
    ) and not getattr(settings, 'XAUTH_EXPOSE_VERBOSE_ERRORS', settings.DEBUG):
        userIdent = user.email if user is not None and isinstance(user, User) and user.is_authenticated else 'unauth'
        logger.info(f"Access denied reason user {userIdent}: {reason}")
        return 'check log for details'

    return reason


def objectAccessValidate(
    objects,
    accessName,
    model=None,
    user=None,
    request: HttpRequest | None = None,
    viewName: str = '',
    returnBool: bool = False,
    returnError: bool = False,
) -> list[object]:
    acc, user = _getAccAndUser(accessName, user=user, request=request)
    if not acc:  # At least one permission MUST be present. Empty permissions are not acceptable
        return False  # _getAccAndUser throws for us if returnBool=False

    # Check object access on actual objects
    ret = []
    for o in objects:
        if not acc.checkObject(user, o, model, request):
            if returnError:
                if returnBool:
                    return False
                raise PermissionException(
                    f"Permission denied for object {viewName or accessName}! Requires {filteredReason(acc, user, o, model)}"
                )

            continue

        ret.append(o)

    return ret


def getFieldFilters(accessName: str, fieldNames: list[str]) -> dict[str, list[Any]]:
    """Returns list of filters which should be gated, along with a list of associated permission objects for each, as a tuple"""

    acc, _ = _getAccAndUser(accessName, user=None, request=None)
    if not acc:
        raise PermissionException(f"Permissions not defined for `{accessName}`")

    existingFields = set(fieldNames)  # For correctness check
    filters: dict[str, list[Any]] = defaultdict(list)

    fieldsAndIfNot = acc.getFieldExcludeFilters()
    if fieldsAndIfNot:
        if not isinstance(fieldsAndIfNot, list):
            fieldsAndIfNot = [fieldsAndIfNot]

        for fields, ifnot in fieldsAndIfNot:
            # Add exclude condition to all fields
            for f in fields:
                if f not in fieldNames:
                    raise PermissionException(f"Exclusion placed on non-existing field {f} on object {accessName}")
                if isinstance(ifnot, list):
                    filters[f] += ifnot
                else:
                    filters[f].append(ifnot or [])

    fieldsAndIfNot = acc.getFieldOnlyFilters()
    if fieldsAndIfNot:
        if not isinstance(fieldsAndIfNot, list):
            fieldsAndIfNot = [fieldsAndIfNot]

        for fields, ifnot in fieldsAndIfNot:
            # Add exclude condition to other fields
            for f in fields:
                if f not in fieldNames:
                    raise PermissionException(f"`Only` placed on non-existing field {f} on object {accessName}")
            for f in existingFields - set(fields):
                if isinstance(ifnot, list):
                    filters[f] += ifnot
                else:
                    filters[f].append(ifnot or [])

    return {k: None if not v else v[0] if len(v) == 1 else AccessAnd(*v) for k, v in filters.items()}


def checkFieldFilters(
    filters,
    fieldName,
    obj,
    accessName,
    model,
    user=None,
    request=None,
    returnBool: bool = False,
) -> bool:
    """Check permissions for a field generated by 'getFieldFilters'"""
    acc, user = _getAccAndUser(accessName, user=user, request=request)
    if not acc:  # At least one permission MUST be present. Empty permissions are not acceptable
        return False  # _getAccAndUser throws for us if returnBool=False

    # If no filter is present, the filter fails, enabling conditionless filtering
    if not filters:
        return False

    # Run object checks as well here. Object checks can be specialized for field checks
    if not filters.checkUser(user, request) or not filters.checkObject(user, obj, model, request):
        if returnBool:
            return False
        raise PermissionException(
            f"Permission denied for field {fieldName} on object {accessName}. Requires {filteredReason(acc, user, obj, model)}"
        )

    return True


def containsObjectCheck(accessName: str) -> bool:
    """Checks if the access check requires an object check"""
    acc, _ = _getAccAndUser(accessName, user=None, request=None)
    if not acc:  # At least one permission MUST be present. Empty permissions are not acceptable
        return False  # _getAccAndUser throws for us if returnBool=False

    return acc.isObjectCheck()


def request_passes_test(test_func: Callable, login_url: str | None = None, redirect_field_name: str | None = None) -> Callable:
    """
    Modified version of Django's user_passes_test, passing request to test_func instead of sending user
    """

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if test_func(request):
                return view_func(request, *args, **kwargs)
            return redirectToLogin(request, login_url=login_url, redirect_field_name=redirect_field_name)

        return _wrapped_view

    return decorator


def viewAccess(accessName: str, formatArgs: Any | None = None, redirect: bool = True) -> Callable:
    """
    Returns view decorator
    :param formatArgs: pass in function with request as argument, providing format args to accessName
    :param redirect: redirect to login on error
    """
    # Dummy fetch permissions to make sure selected permissions are defined, allowing an early error
    if not getattr(settings, 'XAUTH_CHECKS_DISABLE', False) and formatArgs is None:
        _getAccAndUser(accessName, user=None, request=None)

    def decorator(function=None):
        def evaluate(request):
            if formatArgs is not None:
                args = formatArgs(request)
                accessName_ = accessName.format(**args)
            else:
                accessName_ = accessName

            return checkAccess(accessName_, request=request, returnBool=True)

        if redirect:
            # Modified version of django's decorator. Redirects to login on error
            actual_decorator = request_passes_test(evaluate)
            if function:
                return actual_decorator(function)
            return actual_decorator

        # Impl is used if redirect to login is not requested
        def impl(request, *args, **kwargs):
            if evaluate(request):
                return function(request, *args, **kwargs)
            return HttpResponse('Unauthorized', status=401)

        return impl

    return decorator


def userIdentStr(user: User | AnonymousUser | None = None, request: HttpRequest | None = None) -> str:
    user = user if user is not None else request.user if request is not None else None
    return (
        '<null>'
        if user is None
        else ('<anonymous>' if user.is_anonymous else f'"{user.email}"' if user.email else '<blank-email>')
    )
