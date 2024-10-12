# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~

import logging
from typing import TYPE_CHECKING, Optional, Union, cast

from django.conf import settings
from django.db import connection
from django.db.models import F, Model, Q
from django.http import HttpRequest

from ...utils.execenv import isEnvProduction, isEnvTest
from ...utils.listutils import removeDuplicates
from .exceptions import PermissionConfigurationException, PermissionException

if TYPE_CHECKING:
    from django.contrib.auth.models import (  # Only used for type checking, so pylint: disable=imported-auth-user
        AnonymousUser,
        User,
    )

logger = logging.getLogger(__name__)


def _getAccAndUser(
    accessName: str,
    user: Union['User', 'AnonymousUser', None] = None,
    request: HttpRequest | None = None,
):
    permissions = getattr(settings, 'XAUTH_PERMISSIONS')

    acc = permissions.get(accessName, None)

    if not acc:  # At least one permission MUST be present. Empty permissions are not acceptable
        raise PermissionException(f"Permissions not defined for `{accessName}`")

    if isinstance(acc, (list, tuple)):
        acc = AccessAnd(*acc)  # Tuple is implicit and
    else:
        acc = AccessAnd(acc)

    if not user and request:
        # Get user from request if available
        if hasattr(request, 'user') and request.user:
            user = request.user

    return acc, user


def _checkAccess(acc: 'AccessBase', user: 'User', request: HttpRequest | None = None):
    return acc.checkUser(user, request)


def _objectAccessValidation(obj, acc, user, model, request=None):
    return acc.checkObject(user, obj, model, request)


def _objectAccessFilter(acc, user, model, request=None):
    return acc.querySetFilter(user, model, request)


def _objectAccessAnnotate(acc, model):
    return acc.querySetAnnotate(model)


def objectAccessAttributes(accessName, model):
    """Returns object attributes to be queried to determine permissions. Useful for making sure these are prefetched"""
    acc, _ = _getAccAndUser(accessName)
    if not acc:  # At least one permission MUST be present. Empty permissions are not acceptable
        return False  # _getAccAndUser throws for us if returnBool=False

    return removeDuplicates(acc.getObjectAccessAttributes(model))


class AccessBase:
    def checkRequest(self, request: HttpRequest):
        """Convenience alias for checkUser"""
        return self.checkUser(getattr(request, 'user', None), request)

    def isPrivilegeCheck(self):
        """Returns true if test checks for whether user is client, staff, etc. One of these MUST be present for every priv list"""
        return False

    def isUserCheck(self):
        """Returns true if this is a user check"""
        return False

    def isObjectCheck(self):
        """Returns true if this is an object check"""
        return False

    def checkUser(self, user: Optional['User'], request: HttpRequest | None = None):
        """Returns true if user has sufficient privileges to access resource. Some privileges require context/request and will fail unless provided"""
        return True

    def checkObject(
        self,
        user: Optional['User'],
        obj: object,
        model: Model,
        request: HttpRequest | None = None,
    ):
        """For object-level permissions, returns queryset filter for checking permissions. Both this and checkObject should be implemented if one is"""
        return True

    def querySetFilter(self, user: Optional['User'], model: Model, request: HttpRequest | None = None):
        """For object-level permissions, returns queryset filter for checking permissions. Both this and checkObject should be implemented if one is"""
        return ~Q(id=None)  # Q() does not work

    def querySetAnnotate(self, model: Model):
        """Returns a dict of annotations. Ensures that sufficient data is available for 'checkObject'"""
        return {}

    def getFieldExcludeFilters(self):
        return ()

    def getFieldOnlyFilters(self):
        return ()

    def reason(
        self,
        user: Union['User', 'AnonymousUser', None],
        obj=None,
        model: Model | None = None,
        request: HttpRequest | None = None,
    ):
        """Default-reason simply gives the name of the access class that failed"""
        return self.__class__.__name__

    def getUserId(self, user, userIdField):
        if userIdField == 'user':
            return user.id if user is not None else None

        raise PermissionConfigurationException('Invalid userIdField. Choose one of user, ...')

    def _getFieldValue(self, obj, fieldName, expType=None):
        """Field name has format xx__yy, and relies on prefetch. If prefetched value is not present. do regular lookup of permission, which
        will be significantly slower"""

        if hasattr(obj, fieldName):
            return getattr(obj, fieldName)

        # Monitor queries while doing lookup to see if we make additional ones, and warn about it
        q0 = len(connection.queries)
        fieldObj = obj

        for field in fieldName.split('__'):
            fieldObj = getattr(fieldObj, field, None)
        if fieldObj is None:
            raise PermissionException(
                f"{self.__class__.__name__} failed: Model {obj.__class__.__name__} does not have field {fieldName}"
            )
        if expType is not None and not isinstance(fieldObj, expType):
            raise PermissionConfigurationException(f"Value {fieldName} not of correct type")

        if len(connection.queries) > q0:
            logger.warning(
                f"Permissions lookup for {obj.__class__.__name__}.{fieldName} resulted in {len(connection.queries) - q0} extra queries"
            )

        return fieldObj

    def getObjectAccessAttributes(self, model):
        """Returns object attributes to be interrogated"""
        return []


# Permission types
class AccessAnyoneAllowed(AccessBase):
    """Available for anyone"""

    def isPrivilegeCheck(self):
        return True

    def isUserCheck(self):
        return True

    def checkUser(self, user, request=None):
        return True  # Let anyone pass


class AccessPreClientAllowed(AccessBase):
    """Available for clients that are not yet fully onboarded, but have a session with their details"""

    def isPrivilegeCheck(self):
        return True

    def isUserCheck(self):
        return True

    def checkUser(self, user, request=None):
        return user and user.is_active and user.is_authenticated

    def reason(self, user, obj=None, model=None, request=None):
        return 'PreClient'


class AccessClientAllowed(AccessBase):
    """Available for clients. Purpose of class is to explicitly mark that we have checked privileges"""

    UnknownLoggedInUser: type | None = None

    def isPrivilegeCheck(self):
        return True

    def isUserCheck(self):
        return True

    def checkUser(self, user, request=None):
        cls = type(self)

        if cls.UnknownLoggedInUser is None:
            # Cannot resolve type on object creation. Cache it
            from olib.py.django.xauth.accesstypes import UnknownLoggedInUser

            cls.UnknownLoggedInUser = cast(type, UnknownLoggedInUser)

        return user and (
            (user.is_active and user.is_authenticated)
            # We have a valid user, meaning either an admin or a customer signed in
            or isinstance(user, cls.UnknownLoggedInUser)  # pylint: disable=isinstance-second-argument-not-valid-type
        )

    def reason(self, user, obj=None, model=None, request=None):
        return 'Client'


class AccessOnlyStaff(AccessBase):
    def isPrivilegeCheck(self):
        return True

    def isUserCheck(self):
        return True

    def checkUser(self, user, request=None):
        # Quick check first.. Basics
        if not (user and user.is_active and user.is_authenticated and user.is_staff):
            return False

        # Now verify authentication method, to verify that user comes from accepted backend
        if getattr(user, 'backend', '') == 'django.contrib.auth.backends.ModelBackend':
            # User marked as using correct backend
            return True
        # if isinstance(request, RestRequest) and isinstance(request.auth, Token):
        #    # Token is trusted auth method for REST request
        #    return True

        # Rest or regular request. Make sure correct backend is used, i.e. not SHTokenBackend, but ModelBackend,
        # which requires proper username and password
        # Auth backend can be stored in session or on user
        return (
            request is not None
            and hasattr(request, 'session')
            and request.session.get('_auth_user_backend', '') == 'django.contrib.auth.backends.ModelBackend'
        )

    def reason(self, user, obj=None, model=None, request=None):
        return 'Staff'


class AccessOnlySuperuser(AccessOnlyStaff):
    def isPrivilegeCheck(self):
        return True

    def isUserCheck(self):
        return True

    def checkUser(self, user, request=None):
        return super().checkUser(user, request) and user.is_superuser

    def reason(self, user, obj=None, model=None, request=None):
        return 'Superuser'


class AccessOnlyElasticLoadBalancer(AccessBase):
    """Available for calls directly from ELB, e.g. for health checks"""

    def isPrivilegeCheck(self):
        return True  # Good enough alone

    def isUserCheck(self):
        return True

    def checkUser(self, user, request=None):
        # Must have request to pass. The below check for ELB is not perfect, but it at least checks that the IP is on the local network, which should make
        # it harder for others to look at this
        # if request is not None:
        #    logger.info(f'ELB health: {dict(request.META)}')
        #    logger.info(f'ELB checks: {str(request.META.get("HTTP_HOST", None)).startswith("10.0.")}, {str(request.META.get("HTTP_USER_AGENT", None)).startswith("ELB-HealthChecker/")}')
        return (
            request is not None
            and str(request.headers.get('host', None)).startswith('10.0.')
            and str(request.headers.get('user-agent', None)).startswith('ELB-HealthChecker/')
        )

    def reason(self, user, obj=None, model=None, request=None):
        return 'ELB'


class AccessNeverProduction(AccessBase):
    """Not available on production"""

    def checkUser(self, user, request=None):
        return not isEnvProduction()

    def isUserCheck(self):
        return True

    def reason(self, user, obj=None, model=None, request=None):
        return 'Not-Production'


# class AccessOnlyStage(AccessBase):
#     """Not available on production"""

#     def checkUser(self, user, request=None):
#         return isEnvStaging()

#     def isUserCheck(self):
#         return True

#     def reason(self, user, obj=None, model=None, request=None):
#         return 'Stage'


class AccessOnlyTest(AccessBase):
    """Only available during unittests"""

    def checkUser(self, user, request=None):
        return isEnvTest()

    def isUserCheck(self):
        return True

    def reason(self, user, obj=None, model=None, request=None):
        return 'Only-Test'


class AccessOnlyDebug(AccessBase):
    """Only available during unittests"""

    def checkUser(self, user, request=None):
        return settings.DEBUG

    def isUserCheck(self):
        return True

    def reason(self, user, obj=None, model=None, request=None):
        return 'Only-Debug'


class AccessHasContext(AccessBase):
    """Available whenever given context is available and not None"""

    def __init__(self, contextAttrName):
        self.contextAttrName = contextAttrName

    def isUserCheck(self):
        return True

    def checkUser(self, user, request=None):
        return request is not None and getattr(request, self.contextAttrName, None) is not None

    def reason(self, user, obj=None, model=None, request=None):
        return f"Context {self.contextAttrName}"


class AccessPass(AccessBase):
    """Always passes. Cannot be used for views. For those, use AccessAnyoneAllowed"""

    def isUserCheck(self):
        return True


class AccessDeny(AccessBase):
    """Always fails."""

    def isUserCheck(self):
        return True

    def checkUser(self, user, request=None):
        return False

    def reason(self, user, obj=None, model=None, request=None):
        return 'Always denied'


class AccessOr(AccessBase):
    REASON_SEP = ' OR '

    def __init__(self, *accs):
        self._accs = accs

    @property
    def accs(self):
        return self._accs

    def isPrivilegeCheck(self):
        return all(p.isPrivilegeCheck() for p in self.accs)

    def isUserCheck(self):
        # Return True if no accs, because no accs is illegal and we want it go get caught by NOT component if in use
        return any(p.isUserCheck() for p in self.accs) if self.accs else True

    def isObjectCheck(self):
        # Return True if no accs, because no accs is illegal and we want it go get caught by NOT component if in use
        return any(p.isObjectCheck() for p in self.accs) if self.accs else True

    def checkUser(self, user, request=None):
        if not self.accs:
            raise PermissionConfigurationException('Empty AccessOr not allowed')
        return any(p.checkUser(user, request) for p in self.accs)

    def checkObject(self, user, obj, model, request=None):
        if not self.accs:
            raise PermissionConfigurationException('Empty AccessOr not allowed')
        return any(p.checkUser(user, request) and p.checkObject(user, obj, model, request) for p in self.accs)

    def querySetFilter(self, user, model, request=None):
        if not self.accs:
            raise PermissionConfigurationException('Empty AccessOr not allowed')

        ret = None
        for p in self.accs:
            if p.checkUser(user, request):
                f = p.querySetFilter(user, model, request)
            else:
                f = Q(id=None)  # Always false. Access test did not pass

            if f is not None:
                ret = (ret | f) if ret is not None else f
        return ret

    def querySetAnnotate(self, model):
        ret = {}
        for p in self.accs:
            ann = p.querySetAnnotate(model)
            if ann:
                ret.update(ann)
        return ret

    def getFieldExcludeFilters(self):
        # NOTE: Should likely be more sophisticated in the future. OR/AND not respected here
        # Simply accumulate rules
        ret = []
        for p in self.accs:
            v = p.getFieldExcludeFilters()
            if v:
                if isinstance(v, list):
                    ret += v
                else:
                    ret.append(v)

        return ret

    def getFieldOnlyFilters(self):
        ret = []
        for p in self.accs:
            v = p.getFieldOnlyFilters()
            if v:
                if isinstance(v, list):
                    ret += v
                else:
                    ret.append(v)

        return ret

    def reason(self, user, obj=None, model=None, request=None):
        subReasons = []
        for p in self.accs:
            sub = p.reason(user, obj, model, request)
            if sub[-1] != '!':
                # Not marked as failed already.. Check if it failed
                if not (p.checkUser(user, request) and (not obj or p.checkObject(user, obj, model, request))):
                    # Failed
                    sub += '!'

            subReasons.append(sub)

        ret = self.REASON_SEP.join(subReasons)

        if len(self.accs) > 1:
            return f"({ret})"

        return ret

    def getObjectAccessAttributes(self, model):
        return [attr for acc in self.accs for attr in acc.getObjectAccessAttributes(model)]


class AccessAnd(AccessOr):
    REASON_SEP = ' AND '

    def isPrivilegeCheck(self):
        return any(p.isPrivilegeCheck() for p in self.accs)

    def checkUser(self, user, request=None):
        if not self.accs:
            raise PermissionConfigurationException('Empty AccessAnd not allowed')
        return all(p.checkUser(user, request) for p in self.accs)

    def checkObject(self, user, obj, model, request=None):
        if not self.accs:
            raise PermissionConfigurationException('Empty AccessAnd not allowed')
        return all(p.checkUser(user, request) and p.checkObject(user, obj, model, request) for p in self.accs)

    def querySetFilter(self, user, model, request=None):
        if not self.accs:
            raise PermissionConfigurationException('Empty AccessAnd not allowed')

        ret = None
        for p in self.accs:
            if p.checkUser(user, request):
                f = p.querySetFilter(user, model, request)
            else:
                f = Q(id=None)  # Always false. Access test did not pass

            if f is not None:
                ret = (ret & f) if ret is not None else f
        return ret


class AccessNot(AccessBase):
    """Invert access result of provided acc"""

    def __init__(self, acc):
        self.acc = acc

    def isPrivilegeCheck(self):
        return self.acc.isPrivilegeCheck()

    def isUserCheck(self):
        return self.acc.isUserCheck()

    def isObjectCheck(self):
        return self.acc.isObjectCheck()

    def checkUser(self, user, request=None):
        if self.isUserCheck():
            return not self.acc.checkUser(user, request)

        return AccessBase.checkUser(self, user, request)

    def checkObject(self, user, obj, model, request=None):
        if self.isObjectCheck():
            return not self.acc.checkObject(user, obj, model, request)

        return AccessBase.checkObject(self, user, obj, model, request)

    def querySetFilter(self, user, model, request=None):
        if self.isObjectCheck():
            return ~self.acc.querySetFilter(user, model, request)

        return AccessBase.querySetFilter(self, user, model, request)

    def querySetAnnotate(self, model):
        return self.acc.querySetAnnotate(model)

    def reason(self, user, obj=None, model=None, request=None):
        return '~' + self.acc.reason(user, obj, model, request)

    def getFieldExcludeFilters(self):
        if self.acc.getFieldExcludeFilters():
            raise PermissionConfigurationException(
                'Field (exclude) filter not implemented for NOT expression (does it even make sense?)'
            )

    def getFieldOnlyFilters(self):
        if self.acc.getFieldOnlyFilters():
            raise PermissionConfigurationException(
                'Field (only) filter not implemented for NOT expression (does it even make sense?)'
            )

    def getObjectAccessAttributes(self, model):
        return self.acc.getObjectAccessAttributes(model)


class AccessRef(AccessAnd):
    """A ref is like an AND rule, but references another rule"""

    def __init__(self, accessName):
        super().__init__()
        self.accessName = accessName

    @property
    def accs(self):
        permissions = getattr(settings, 'XAUTH_PERMISSIONS')
        acc = permissions.get(self.accessName, None)

        if not acc:
            raise PermissionConfigurationException(f"Unknown Access Name `{self.accessName}` in ref")
        if not isinstance(acc, (list, tuple)):
            raise PermissionConfigurationException(
                f"Permissions must be in list form. Invalid permissions for Access Name {self.accessName} in ref"
            )
        return acc

    def getObjectAccessAttributes(self, model):
        return objectAccessAttributes(self.accessName, model)


class AccessPermissions(AccessBase):
    """Global permissions"""

    def __init__(self, *permissions):
        self.permissions = permissions

    def isUserCheck(self):
        return True

    def checkUser(self, user, request=None):
        return user and user.is_active and user.is_authenticated and user.has_perms(self.permissions)

    def reason(self, user, obj=None, model=None, request=None):
        isAuth = user and user.is_active and user.is_authenticated
        return format(
            ' AND '.join([p + ('!' if not isAuth or not user.has_perms([p]) else '') for p in self.permissions])
        )


class AccessIsOwner(AccessBase):
    """
    Only allow access by owner of object. Preferably define ownership on DB model using '_ownership = (<fieldName>, <userIdField>)' field
    fieldName can be pointing to subclass. userIdField is one of 'user', 'user' or 'shcustomer'
    """

    def __init__(self, fieldName=None, userIdField=None, ifnot=None):
        self.ownership: tuple[str, str] | None

        if fieldName or userIdField:
            if not (fieldName and userIdField):
                raise PermissionConfigurationException('Must set either both fieldName and userIdField or none')

            self.ownership = (fieldName, userIdField)
        else:
            # Take ownership from model
            self.ownership = None

        self.ifnot = AccessAnd(*ifnot) if isinstance(ifnot, (tuple, list)) else ifnot

    def isObjectCheck(self):
        return True

    def checkObject(self, user, obj, model, request=None):
        if (
            self.ifnot
            and _checkAccess(self.ifnot, user, request)
            and _objectAccessValidation(obj, self.ifnot, user, model, request)
        ):
            # Ifnot condition passed
            return True

        if isinstance(obj, dict):
            # Non-object. Can be marked as owned
            return obj.get('_isOwner', False)

        if getattr(obj, '_isOwner', False):
            # Previously marked as owned
            return True

        if model is None:
            # Non-model object which is not previously marked will fail ownership access test
            return False
            # raise PermissionConfigurationException(f'Ownership permissions cannot be applied to non-model objects: {obj.__class__.__name__}')

        ownership = self.ownership or model._ownership  # pylint: disable=protected-access

        id = self.getUserId(user, ownership[1])
        ownerId = self._getFieldValue(obj, ownership[0], int)
        isOwner_ = ownerId is not None and ownerId == id

        # Purpose of _isOwner is to signal to framework that ownership check passed. We don't want to set _isOwner, as
        # that would make checks for multiple users on the same object fail.
        obj._isOwnerSub = isOwner_  # pylint: disable=protected-access

        return isOwner_

    def querySetFilter(self, user, model, request=None):
        ownership = self.ownership or model._ownership  # pylint: disable=protected-access
        id = self.getUserId(user, ownership[1])  # pylint: disable=protected-access
        q = Q(**{ownership[0] + '__isnull': False}) & Q(**{ownership[0]: id})

        if self.ifnot and _checkAccess(self.ifnot, user, request):  # pylint: disable=protected-access
            # Apply ifnot condition
            f = _objectAccessFilter(self.ifnot, user, model, request)
            return Q(q | f)

        return q

    def querySetAnnotate(self, model):
        # If nested fieldname, annotate so we get access to it on the object, so checkObject works
        ownership = self.ownership or model._ownership  # pylint: disable=protected-access
        if '__' in ownership[0]:  # pylint: disable=protected-access
            return {ownership[0]: F(ownership[0])}

        return {}

    def reason(self, user, obj=None, model=None, request=None):
        return 'Owned'

    def getObjectAccessAttributes(self, model):
        # pylint: disable=protected-access
        attr = [(self.ownership[0] if self.ownership is not None else model._ownership[0])]
        # pylint: enable=protected-access
        if self.ifnot:
            attr += self.ifnot.getObjectAccessAttributes(model)
        return attr


class AccessIsOwnerOrNoOwner(AccessIsOwner):
    """If ownership field is set, then only allow access by the owner"""

    def checkObject(self, user, obj, model, request=None):
        if super().checkObject(user, obj, model, request):
            return True
        ownership = self.ownership or model._ownership  # pylint: disable=protected-access
        ownerId = self._getFieldValue(obj, ownership[0], int)
        return ownerId is None

    def querySetFilter(self, user, model, request=None):
        ownership = self.ownership or model._ownership  # pylint: disable=protected-access
        id = self.getUserId(user, ownership[1])  # pylint: disable=protected-access
        # Ok if no owner or owner is the one given by id. If id is not available, the second check also becomes a check for None
        q = Q(**{ownership[0]: None}) | Q(**{ownership[0]: id})

        if self.ifnot and _checkAccess(self.ifnot, user, request):  # pylint: disable=protected-access
            # Apply ifnot condition
            f = _objectAccessFilter(self.ifnot, user, model, request)
            return Q(q | f)

        return q

    def reason(self, user, obj=None, model=None, request=None):
        return 'Owned-or-not'


class AccessIfFieldValues(AccessBase):
    """Give access if fields have certain values. Also works for dictionaries"""

    def __init__(self, **fieldsAndValues):
        self.fieldsAndValues = fieldsAndValues
        self.qFilter = Q(**fieldsAndValues)  # Assemble filter once

    def isObjectCheck(self):
        return True

    def checkObject(self, user, obj, model, request=None):
        if isinstance(obj, dict):
            # Dictionary
            for field, expValue in self.fieldsAndValues.items():
                if obj[field] != expValue:
                    return False
        else:
            # Model
            for field, expValue in self.fieldsAndValues.items():
                value = self._getFieldValue(obj, field)
                if value != expValue:
                    return False
        return True

    def querySetFilter(self, user, model, request=None):
        return self.qFilter

    def reason(self, user, obj=None, model=None, request=None):
        params = ', '.join([f"{k}={v}" for k, v in self.fieldsAndValues.items()])
        return f"Object-fields: ({params})"

    def getObjectAccessAttributes(self, model):
        return self.fieldsAndValues.keys()


class AccessValueEquals(AccessBase):
    """Typically used on none-object values. Checks if value is one of the given"""

    def __init__(self, *allowedValues):
        self.allowedValues = set(allowedValues)

    def isObjectCheck(self):
        return True

    def checkObject(self, user, obj, model, request=None):
        return obj in self.allowedValues

    def querySetFilter(self, user, model, request=None):
        raise PermissionConfigurationException(
            'AccessValueEquals cannot be used on models'
        )  # Does not filter db values


class AccessExcludeFields(AccessBase):
    def __init__(self, *fields, ifnot=None):
        self.fields = fields
        self.ifnot = AccessAnd(*ifnot) if isinstance(ifnot, (tuple, list)) else ifnot

    def isObjectCheck(self):
        return True

    def getFieldExcludeFilters(self):
        return (self.fields, self.ifnot)

    def getObjectAccessAttributes(self, model):
        return self.ifnot.getObjectAccessAttributes(model)


class AccessOnlyFields(AccessBase):
    def __init__(self, *fields, ifnot=None):
        self.fields = fields
        self.ifnot = AccessAnd(*ifnot) if isinstance(ifnot, (tuple, list)) else ifnot

    def isObjectCheck(self):
        return True

    def getFieldOnlyFilters(self):
        return (self.fields, self.ifnot)

    def getObjectAccessAttributes(self, model):
        return self.ifnot.getObjectAccessAttributes(model)


ok = AccessPass()
anyone = AccessAnyoneAllowed()
preclient = AccessPreClientAllowed()
client = AccessClientAllowed()  # Logged in user
staff = AccessOnlyStaff()
superuser = AccessOnlySuperuser()
elb = AccessOnlyElasticLoadBalancer()
perm = AccessPermissions
isOwnerOrNoOwner = AccessIsOwnerOrNoOwner
isOwner = AccessIsOwner
ifFields = AccessIfFieldValues
excludeFields = AccessExcludeFields
onlyFields = AccessOnlyFields
neverProduction = AccessNeverProduction()
onlyTest = AccessOnlyTest()
onlyDebug = AccessOnlyDebug()
hasContext = AccessHasContext
or_ = AccessOr
and_ = AccessAnd
ref = AccessRef
equals = AccessValueEquals  # Use to constrain non-model values
not_ = AccessNot
deny = AccessDeny()
