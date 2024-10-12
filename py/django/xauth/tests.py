# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~

import logging
from typing import Any, cast

from django.contrib.auth import get_user_model

# import texttable as tt
from django.test import RequestFactory, tag
from django.test.utils import override_settings
from rich.console import Console
from rich.table import Table

from olib.py.django.test import createUser
from olib.py.django.test.cases import OTestCase
from olib.py.django.test.models import TestXAuthOwnedModel, TestXAuthParentModel
from olib.py.django.xauth.accesstypes import UnknownLoggedInUser
from olib.py.django.xauth.authorization import (
    applyObjectAccessFilter,
    assumeAdminLoggedIn,
    checkAccess,
    checkFieldFilters,
    containsObjectCheck,
    getFieldFilters,
    objectAccessAttributes,
    objectAccessFilter,
    objectAccessValidate,
    viewAccess,
)
from olib.py.django.xauth.exceptions import (
    PermissionConfigurationException,
    PermissionException,
)
from olib.py.django.xauth.primitives import (
    _checkAccess,
    _objectAccessAnnotate,
    _objectAccessValidation,
    and_,
    anyone,
    client,
    deny,
    elb,
    equals,
    excludeFields,
    hasContext,
    ifFields,
    isOwner,
    isOwnerOrNoOwner,
    neverProduction,
    not_,
    ok,
    onlyDebug,
    onlyFields,
    onlyTest,
    or_,
    perm,
    preclient,
    ref,
    staff,
    superuser,
)
from olib.py.test.mock import MockRequest
from olib.py.utils.execenv import ExecContext, ExecEnv, initExecEnv

logger = logging.getLogger(__name__)
User = get_user_model()


@tag('olib')
class TestAccess(OTestCase):
    """Tests raw access components, making sure their behavior is correct"""

    OTHER_PERMS = {'_gql__errorMessagesOnProduction': superuser}

    def test_accessComponents(self):
        """Test every check method on each access object, including options like ifnot"""

        # Set up users
        users = [
            None,
            # Clients
            createUser('c0', password='p1'),
            createUser('c1', password='p1'),
            createUser('c2', password='p1', is_staff=True),  # Staff, but client login. Does not get staff privs
            # Staff
            createUser('s0', password='p1', is_staff=True),
            createUser('s1', password='p1', is_staff=True),
            # Staff with perms
            createUser(
                'p0',
                password='p2',
                is_staff=True,
                permissions=('view_testxauthownedmodel',),
            ),
            createUser(
                'p1',
                password='p2',
                is_staff=True,
                permissions=(
                    'view_testxauthownedmodel',
                    'change_testxauthownedmodel',
                ),
            ),
            # Super
            createUser('x0', password='p3', is_staff=True, is_superuser=True),
        ]

        userByName = {u.username if u else 'nn': u for u in users}

        #'DummyClientBackend' is not an actual backend, but is used to represent a lesser backend which cannot give staff/superuser privs.
        # None pased into backend results in the default backend.
        requests = [
            MockRequest(
                u,
                backend=('DummyClientBackend' if u is not None and u.username.startswith('c') else None),
            )
            for u in users
        ]
        # Make sure mock requests preserves 'customAttr' attribute if present. It is used in this test for checking for specific context attributes on the request
        for r in requests:
            r.attrNames.add('customAttr')

        # Data to test on. Different objects, ownership types, etc.
        TestXAuthOwnedModel.objects.bulk_create(
            [
                TestXAuthOwnedModel(value='typeA'),
                TestXAuthOwnedModel(value='typeA', owner=userByName['c0'], staff_only=False),
                TestXAuthOwnedModel(value='typeB', owner=userByName['c1'], staff_only=True),
                TestXAuthOwnedModel(value='typeB', owner=userByName['s0'], staff_only=True),
            ]
        )

        TestXAuthParentModel.objects.bulk_create(
            [TestXAuthParentModel(owned=m) for m in TestXAuthOwnedModel.objects.order_by('id')]
        )

        #     SHOrder.objects.create(id=1)  #customer ownership
        #     createOrder(userByName['c0'])
        #     createOrder(userByName['c1'])
        #     createOrder(userByName['s0'])
        #     m0 = Mail.objects.create(topic='x', subject='x', from_email='x', to_email='x', html='x', txt='x', to_user=None)             #user ownership
        #     Mail.objects.create(topic='x', subject='x', from_email='x', to_email='x', html='x', txt='x', to_user=userByName['c0'])
        #     Mail.objects.create(topic='x', subject='x', from_email='x', to_email='x', html='x', txt='x', to_user=userByName['c1'])
        #     Mail.objects.create(topic='x', subject='x', from_email='x', to_email='x', html='x', txt='x', to_user=userByName['s0'])

        #     #Since object ids vary by test, get offset so we can subtract
        offsetByModel = {
            TestXAuthOwnedModel: (
                first.id - 1 if (first := TestXAuthOwnedModel.objects.order_by('id').first()) is not None else 0
            ),
            TestXAuthParentModel: (
                first.id - 1 if (first := TestXAuthParentModel.objects.order_by('id').first()) is not None else 0
            ),
            # SHOrder: 0,
            # Mail: m0.id - 1
        }

        # Test modifiers
        settings = lambda **d: ('settings', d, None, None, None)
        settingsClear = lambda: ('settingsClear', None, None, None, None)

        execEnv = lambda **d: ('execEnv', d, None, None, None)
        execEnvClear = lambda: ('execEnvClear', None, None, None, None)

        headers = lambda d: ('headers', d, None, None, None)
        headersClear = lambda: ('headersClear', None, None, None, None)

        setContext = lambda **d: ('context', d, None, None, None)
        excludeCheck = lambda excludes: ('exclude', excludes, None, None, None)

        # setFeatureAccess = lambda **d: ('featureAccess', d, None, None, None)

        extraPermissions = lambda **permissions: (
            'permissions',
            permissions,
            None,
            None,
            None,
        )

        # In tests results, <username> alone means that the user gets all objects. <username>:12 means that the user got objects 1 and 2
        # Fields are simplified to a,b,c,d, and if user has access to all fields, no mention, else fields with access are appended, e.g. <username>:<objs>^ab
        # fmt: off
        tests: list[Any] = [
            #Basics, standalone permissions
            (TestXAuthOwnedModel, (ok, ),                                                  'Privilege check not done for view access-name',             False, 'Ok allowed as sub-condition, but not as top-level permission. Should fail'),
            (TestXAuthOwnedModel, (deny, ),                                                [],                                                          False, 'Deny allowed as sub-condition, but not as top-level permission. Should fail'),
            (TestXAuthOwnedModel, (anyone, ),                                              ['nn', 'c0', 'c1', 'c2', 's0', 's1', 'p0', 'p1', 'x0'],      False, 'Outsider also allowed'),
            (TestXAuthOwnedModel, (preclient, ),                                           ['c0', 'c1', 'c2', 's0', 's1', 'p0', 'p1', 'x0'],            False, 'Preclient is superset of client'),
            (TestXAuthOwnedModel, (client, ),                                              ['c0', 'c1', 'c2', 's0', 's1', 'p0', 'p1', 'x0'],            False, 'Any authenticated allowed'),
            (TestXAuthOwnedModel, (staff, ),                                               ['s0', 's1', 'p0', 'p1', 'x0'],                              False, 'Only staff'),
            (TestXAuthOwnedModel, (superuser, ),                                           ['x0'],                                                      False, 'Only superuser'),
            (TestXAuthOwnedModel, (perm('test.view_testxauthownedmodel'), ),                            'Privilege check not done for view access-name',             False, 'Perm alone not enough. Should fail (1)'),
            (TestXAuthOwnedModel, (neverProduction, ),                                     'Privilege check not done for view access-name',             False, 'Perm alone not enough. Should fail (2)'),
            #(TestXAuthOwnedModel, (onlyStage, ),                                           [],                                                          False, 'onlyStage check fails before priv-present check'),
            (TestXAuthOwnedModel, (hasContext('customAttr'), ),                                   [],                                                          False, 'Context check fails before priv-present check'),
            (TestXAuthOwnedModel, (or_(), ),                                               'Empty AccessOr not allowed',                                True, 'Perm alone not enough. Should fail (5)'),
            (TestXAuthOwnedModel, (and_(), ),                                              'Empty AccessAnd not allowed',                               True, 'Perm alone not enough. Should fail (6)'),
            (TestXAuthOwnedModel, (ref(''), ),                                             'Unknown Access Name `` in ref',                   'Unknown Access Name `` in ref', 'Empty permissions. Should fail'),
            (TestXAuthOwnedModel, (isOwnerOrNoOwner('owner_id', 'user'), ),               'Privilege check not done for view access-name',             True, 'Perm alone not enough. Should fail (8)'),
            (TestXAuthOwnedModel, (isOwner('owner_id', 'user'), ),                        'Privilege check not done for view access-name',             True, 'Perm alone not enough. Should fail (9)'),
            (TestXAuthOwnedModel, (ifFields(staff_only=False), ),                          'Privilege check not done for view access-name',             True, 'Perm alone not enough. Should fail (10)'),
            (TestXAuthOwnedModel, (ifFields(staff_only=True), ),                           'Privilege check not done for view access-name',             True, 'Perm alone not enough. Should fail (11)'),
            (TestXAuthOwnedModel, (excludeFields('a'), ),                                  'Privilege check not done for view access-name',             True, 'Perm alone not enough. Should fail (12)'),
            (TestXAuthOwnedModel, (onlyFields('a'), ),                                     'Privilege check not done for view access-name',             True, 'Perm alone not enough. Should fail (13)'),
            (TestXAuthOwnedModel, (equals(1), ),                                           'Privilege check not done for view access-name',             True, 'Cannot be used on models'), #Tested further in other test

            #Inversion tests
            (TestXAuthOwnedModel, (not_(ok), ),                                                  [],                                                          False, '(NOT ok) Allowed as sub-condition, but not as top-level permission. Should fail'),
            (TestXAuthOwnedModel, (not_(deny), ),                                                'Privilege check not done for view access-name',             False, '(NOT deny) Allowed as sub-condition, but not as top-level permission. Should fail'),
            (TestXAuthOwnedModel, (not_(anyone), ),                                              [],                                                          False, '(NOT) Outsider also allowed'),
            (TestXAuthOwnedModel, (not_(preclient), ),                                           ['nn'],                                                      False, '(NOT) Preclient is superset of client'),
            (TestXAuthOwnedModel, (not_(client), ),                                              ['nn'],                                                      False, '(NOT) Any authenticated allowed'),
            (TestXAuthOwnedModel, (not_(staff), ),                                               ['nn', 'c0', 'c1', 'c2'],                                    False, '(NOT) Only staff'),
            (TestXAuthOwnedModel, (not_(superuser), ),                                           ['nn', 'c0', 'c1', 'c2', 's0', 's1', 'p0', 'p1'],            False, '(NOT) Only superuser'),
            (TestXAuthOwnedModel, (not_(perm('test.view_testxauthownedmodel')), ),                            'Privilege check not done for view access-name',             False, '(NOT) Perm alone not enough. Should fail (1)'),
            (TestXAuthOwnedModel, (not_(neverProduction), ),                                     [],                                                          False, '(NOT) Perm alone not enough. Should fail (2)'),
            #(TestXAuthOwnedModel, (not_(onlyStage), ),                                           'Privilege check not done for view access-name',             False, '(NOT) Perm alone not enough. Should fail (3)'),
            (TestXAuthOwnedModel, (not_(hasContext('customAttr')), ),                                   'Privilege check not done for view access-name',             False, '(NOT) Context check fails before priv-present check'),
            (TestXAuthOwnedModel, (not_(or_()), ),                                               'Empty AccessOr not allowed',                                True, '(NOT) Perm alone not enough. Should fail (4)'),
            (TestXAuthOwnedModel, (not_(and_()), ),                                              'Empty AccessAnd not allowed',                               True, '(NOT) Perm alone not enough. Should fail (5)'),
            (TestXAuthOwnedModel, (not_(ref('')), ),                                             'Unknown Access Name `` in ref',                   'Unknown Access Name `` in ref', 'Empty permissions. Should fail'),
            (TestXAuthOwnedModel, (not_(isOwnerOrNoOwner('owner_id', 'user')), ),               'Privilege check not done for view access-name',          True, '(NOT) Perm alone not enough. Should fail (7)'),
            (TestXAuthOwnedModel, (not_(isOwner('owner_id', 'user')), ),                        'Privilege check not done for view access-name',          True, '(NOT) Perm alone not enough. Should fail (8)'),
            (TestXAuthOwnedModel, (not_(ifFields(staff_only=False)), ),                          'Privilege check not done for view access-name',          True, '(NOT) Perm alone not enough. Should fail (9)'),
            (TestXAuthOwnedModel, (not_(ifFields(staff_only=True)), ),                           'Privilege check not done for view access-name',          True, '(NOT) Perm alone not enough. Should fail (10)'),
            (TestXAuthOwnedModel, (not_(excludeFields('a')), ),                                  'Privilege check not done for view access-name',          True, '(NOT) Perm alone not enough. Should fail (11)'),
            (TestXAuthOwnedModel, (not_(onlyFields('a')), ),                                     'Privilege check not done for view access-name',          True, '(NOT) Perm alone not enough. Should fail (12)'),
            (TestXAuthOwnedModel, (not_(equals(1)), ),                                           'Privilege check not done for view access-name',          True, '(NOT) Cannot be used on models'), #Tested further in other test


            #Basics, enabling permissions that are not ok standalone
            (TestXAuthOwnedModel, (anyone, perm('test.view_testxauthownedmodel')),                       ['p0', 'p1', 'x0'],                                                         False, 'Proper permissions (0)'),
            (TestXAuthOwnedModel, (anyone, perm('test.change_testxauthownedmodel')),                     ['p1', 'x0'],                                                               False, 'Proper permissions (1)'),
            (TestXAuthOwnedModel, (anyone, perm('test.view_testxauthownedmodel', 'test.change_testxauthownedmodel')), ['p1', 'x0'],                                                               False, 'Proper permissions (2)'),
            (TestXAuthOwnedModel, (anyone, neverProduction, ),                              ['nn', 'c0', 'c1', 'c2', 's0', 's1', 'p0', 'p1', 'x0'],                     False, 'neverproduction ok in test env'),
            #(TestXAuthOwnedModel, (anyone, onlyStage, ),                                    [],                                                                         False, 'onlystage not ok in test env'),
            (TestXAuthOwnedModel, (anyone, hasContext('customAttr'), ),                            [],                                                                         False, 'Does not have context.. should fail for all'),
            (TestXAuthOwnedModel, (anyone, or_()),                                          'Empty AccessOr not allowed',                                               True, 'Empty OR probably a bug. Should fail'),
            (TestXAuthOwnedModel, (anyone, and_()),                                         'Empty AccessAnd not allowed',                                              True, 'Empty AND probably a bug. Should fail'),
            (TestXAuthOwnedModel, (anyone, ok),                                             ['nn', 'c0', 'c1', 'c2', 's0', 's1', 'p0', 'p1', 'x0'],                     False, 'ok'),
            (TestXAuthOwnedModel, (anyone, deny),                                           [],                                                                         False, 'deny'),

            (TestXAuthOwnedModel, (anyone, isOwnerOrNoOwner('owner_id', 'user'), ),        ['nn:1', 'c0:12', 'c1:13', 'c2:1', 's0:14', 's1:1', 'p0:1', 'p1:1', 'x0:1'],        True, 'isOwnerOrNoOwner'),
            (TestXAuthOwnedModel, (anyone, isOwner('owner_id', 'user'), ),                 ['nn:', 'c0:2', 'c1:3', 'c2:', 's0:4', 's1:', 'p0:', 'p1:', 'x0:'],                True, 'isOwner - most users get nothing'),
            (TestXAuthOwnedModel, (anyone, ifFields(staff_only=False), ),                   ['nn:2', 'c0:2', 'c1:2', 'c2:2', 's0:2', 's1:2', 'p0:2', 'p1:2', 'x0:2'],           True, 'staff_only=False.. default in model is True'),
            (TestXAuthOwnedModel, (anyone, ifFields(staff_only=True), ),                    ['nn:134', 'c0:134', 'c1:134', 'c2:134', 's0:134', 's1:134', 'p0:134', 'p1:134', 'x0:134'],   True, 'staff_only=True.. default in model is True'),
            (TestXAuthOwnedModel, (anyone, excludeFields('a','b'), ),                       ['nn^cd', 'c0^cd', 'c1^cd', 'c2^cd', 's0^cd', 's1^cd', 'p0^cd', 'p1^cd', 'x0^cd'],   True, 'excludeFields - basics'),
            (TestXAuthOwnedModel, (anyone, onlyFields('b','c'), ),                          ['nn^bc', 'c0^bc', 'c1^bc', 'c2^bc', 's0^bc', 's1^bc', 'p0^bc', 'p1^bc', 'x0^bc'],   True, 'onlyFields - basics'),

            #Inverted basics
            (TestXAuthOwnedModel, (and_(anyone, not_(perm('test.view_testxauthownedmodel'))), ),                       ['nn', 'c0', 'c1', 'c2', 's0', 's1'],                                               False, '(NOT) Proper permissions (0)'),
            (TestXAuthOwnedModel, (and_(anyone, not_(perm('test.change_testxauthownedmodel'))), ),                     ['nn', 'c0', 'c1', 'c2', 's0', 's1', 'p0'],                                        False, '(NOT) Proper permissions (1)'),
            (TestXAuthOwnedModel, (and_(anyone, not_(perm('test.view_testxauthownedmodel', 'test.change_testxauthownedmodel'))), ), ['nn', 'c0', 'c1', 'c2', 's0', 's1', 'p0'],                                        False, '(NOT) Proper permissions (2)'),
            (TestXAuthOwnedModel, (and_(anyone, not_(neverProduction)), ),                                [],                                                                                False, '(NOT) neverproduction ok in test env'),
            #(TestXAuthOwnedModel, (and_(anyone, not_(onlyStage)), ),                                      ['nn', 'c0', 'c1', 'c2', 's0', 's1', 'p0', 'p1', 'x0'],                            False, '(NOT) onlystage ok in test env'),
            (TestXAuthOwnedModel, (and_(anyone, not_(hasContext('customAttr'))), ),                              ['nn', 'c0', 'c1', 'c2', 's0', 's1', 'p0', 'p1', 'x0'],                            False, '(NOT) Does not have context.. should fail for all'),
            (TestXAuthOwnedModel, (and_(anyone, not_(or_())), ),                                          'Empty AccessOr not allowed',                                                      True, '(NOT) Empty OR probably a bug. Should fail'),
            (TestXAuthOwnedModel, (and_(anyone, not_(and_())), ),                                         'Empty AccessAnd not allowed',                                                     True, '(NOT) Empty AND probably a bug. Should fail'),

            (TestXAuthOwnedModel, (and_(anyone, not_(isOwnerOrNoOwner('owner_id', 'user'))), ),        ['nn:234', 'c0:34', 'c1:24', 'c2:234', 's0:23', 's1:234', 'p0:234', 'p1:234', 'x0:234'],      True, '(NOT) isOwnerOrNoOwner'),
            (TestXAuthOwnedModel, (and_(anyone, not_(isOwner('owner_id', 'user'))), ),                 ['nn', 'c0:134', 'c1:124', 'c2', 's0:123', 's1', 'p0', 'p1', 'x0'],                                 True, '(NOT) isOwner - most users get nothing'),
            (TestXAuthOwnedModel, (and_(anyone, not_(ifFields(staff_only=False))), ),                   ['nn:134', 'c0:134', 'c1:134', 'c2:134', 's0:134', 's1:134', 'p0:134', 'p1:134', 'x0:134'],                     True, '(NOT) staff_only=False.. default in model is True'),
            (TestXAuthOwnedModel, (and_(anyone, not_(ifFields(staff_only=True))), ),                    ['nn:2', 'c0:2', 'c1:2', 'c2:2', 's0:2', 's1:2', 'p0:2', 'p1:2', 'x0:2'],                     True, '(NOT) staff_only=True.. default in model is True'),
            (TestXAuthOwnedModel, (and_(anyone, not_(excludeFields('a','b'))), ),                       ['nn:', 'c0:', 'c1:', 'c2:', 's0:', 's1:', 'p0:', 'p1:', 'x0:'],                              True, '(NOT) excludeFields - basics'),
            (TestXAuthOwnedModel, (and_(anyone, not_(onlyFields('b','c'))), ),                          ['nn:', 'c0:', 'c1:', 'c2:', 's0:', 's1:', 'p0:', 'p1:', 'x0:'],                              True, '(NOT) onlyFields - basics'),



            #Simple composition, basic usecases
            (TestXAuthOwnedModel, (anyone, perm('test.view_testxauthownedmodel'), perm('test.change_testxauthownedmodel')), ['p1', 'x0'],                                         False, 'Proper permissions (simple composition)'),


            #Test real-world usecases
            (TestXAuthOwnedModel, (staff,  isOwnerOrNoOwner('owner_id', 'user')),                    ['s0:14', 's1:1', 'p0:1', 'p1:1', 'x0:1'],                        True, 'isOwner - staff and owner/no-owner'),
            (TestXAuthOwnedModel, (client, isOwner('owner_id', 'user'), ifFields(staff_only=False)), ['c0:2', 'c1:', 'c2:', 's0:', 's1:', 'p0:', 'p1:', 'x0:'],               True, 'isOwner - client and owner/no-owner'),
            (TestXAuthOwnedModel, (client, isOwner('owner_id', 'user'), ifFields(staff_only=True)),  ['c0:', 'c1:3', 'c2:', 's0:4', 's1:', 'p0:', 'p1:', 'x0:'],              True, 'isOwner - owned, but staff_only=True'),
            (TestXAuthOwnedModel, (client, isOwner('owner_id', 'user', ifnot=(staff, perm('test.view_testxauthownedmodel')))), ['c0:2', 'c1:3', 'c2:', 's0:4', 's1:', 'p0', 'p1', 'x0'],   True, 'clients see owned, staff with perms see all'),
            (TestXAuthOwnedModel, (client, ifFields(staff_only=False), isOwner('owner_id', 'user', ifnot=(staff, perm('test.view_testxauthownedmodel')))),
                                                                                               ['c0:2', 'c1:', 'c2:', 's0:', 's1:', 'p0:2', 'p1:2', 'x0:2'],            True, 'clients see owned if not staff_only, staff with perms see all'),

            ###############################
            #Detailed tests

            #IsOwner
            (TestXAuthOwnedModel, (anyone, isOwner('owner_id',    'user')),       ['nn:', 'c0:2', 'c1:3', 'c2:', 's0:4', 's1:', 'p0:', 'p1:', 'x0:'], True, 'isOwner - ownership types: user'),
            (TestXAuthOwnedModel, (anyone, isOwner()),                             ['nn:', 'c0:2', 'c1:3', 'c2:', 's0:4', 's1:', 'p0:', 'p1:', 'x0:'], True, 'isOwner - ownership types: user - model defaults'),

            (TestXAuthParentModel,  (anyone, isOwner()),  ['nn:', 'c0:2', 'c1:3', 'c2:', 's0:4', 's1:', 'p0:', 'p1:', 'x0:'],                            True, 'isOwner - ownership types: nested - model defaults'),
            (TestXAuthParentModel,  (anyone, isOwner('owned__owner_id', 'user')),  ['nn:', 'c0:2', 'c1:3', 'c2:', 's0:4', 's1:', 'p0:', 'p1:', 'x0:'], True, 'isOwner - ownership types: nested'),
            (TestXAuthParentModel,  (anyone, isOwner('owned__owner__id', 'user')), ['nn:', 'c0:2', 'c1:3', 'c2:', 's0:4', 's1:', 'p0:', 'p1:', 'x0:'], True, 'isOwner - ownership types: nested'),

            (TestXAuthOwnedModel, (anyone, isOwner('owner_id', 'user', ifnot=staff)),                               ['nn:', 'c0:2', 'c1:3', 'c2:', 's0', 's1', 'p0', 'p1', 'x0'],      True, 'isOwner - ifnot: single-arg, user-check'),
            (TestXAuthOwnedModel, (anyone, isOwner('owner_id', 'user', ifnot=(staff, superuser))),                  ['nn:', 'c0:2', 'c1:3', 'c2:', 's0:4', 's1:', 'p0:', 'p1:', 'x0'], True, 'isOwner - ifnot: multi-arg, user-check'),
            (TestXAuthOwnedModel, (anyone, isOwner('owner_id', 'user', ifnot=(staff, ifFields(staff_only=True)))),  ['nn:', 'c0:2', 'c1:3', 'c2:', 's0:134', 's1:134', 'p0:134', 'p1:134', 'x0:134'], True, 'isOwner - ifnot: multi-arg, object-check'),
            (TestXAuthOwnedModel, (anyone, isOwner('owner_id', 'user', ifnot=(staff, ifFields(staff_only=True), ifFields(staff_only=False)))),
                                                                                                              ['nn:', 'c0:2', 'c1:3', 'c2:', 's0:4', 's1:', 'p0:', 'p1:', 'x0:'], True, 'isOwner - ifnot: multi-arg, multi-obj.. Cancels out'),


            #IsOwnerOrNoOwner
            (TestXAuthOwnedModel, (anyone, isOwnerOrNoOwner('owner_id',    'user')),        ['nn:1', 'c0:12', 'c1:13', 'c2:1', 's0:14', 's1:1', 'p0:1', 'p1:1', 'x0:1'], True, 'isOwner - ownership types: user'),

            (TestXAuthParentModel, (anyone, isOwnerOrNoOwner()),                             ['nn:1', 'c0:12', 'c1:13', 'c2:1', 's0:14', 's1:1', 'p0:1', 'p1:1', 'x0:1'], True, 'isOwner - ownership types: nested - model defaults'),
            (TestXAuthParentModel, (anyone, isOwnerOrNoOwner('owned__owner_id', 'user')),  ['nn:1', 'c0:12', 'c1:13', 'c2:1', 's0:14', 's1:1', 'p0:1', 'p1:1', 'x0:1'], True, 'isOwner - ownership types: nested'),
            (TestXAuthParentModel, (anyone, isOwnerOrNoOwner('owned__owner__id', 'user')), ['nn:1', 'c0:12', 'c1:13', 'c2:1', 's0:14', 's1:1', 'p0:1', 'p1:1', 'x0:1'], True, 'isOwner - ownership types: nested'),

            (TestXAuthOwnedModel, (anyone, isOwnerOrNoOwner('owner_id', 'user', ifnot=staff)),                               ['nn:1', 'c0:12', 'c1:13', 'c2:1', 's0', 's1', 'p0', 'p1', 'x0'],      True, 'isOwner - ifnot: single-arg, user-check'),
            (TestXAuthOwnedModel, (anyone, isOwnerOrNoOwner('owner_id', 'user', ifnot=(staff, superuser))),                  ['nn:1', 'c0:12', 'c1:13', 'c2:1', 's0:14', 's1:1', 'p0:1', 'p1:1', 'x0'], True, 'isOwner - ifnot: multi-arg, user-check'),
            (TestXAuthOwnedModel, (anyone, isOwnerOrNoOwner('owner_id', 'user', ifnot=(staff, ifFields(staff_only=True)))),  ['nn:1', 'c0:12', 'c1:13', 'c2:1', 's0:134', 's1:134', 'p0:134', 'p1:134', 'x0:134'], True, 'isOwner - ifnot: multi-arg, object-check'),
            (TestXAuthOwnedModel, (anyone, isOwnerOrNoOwner('owner_id', 'user', ifnot=(staff, ifFields(staff_only=True), ifFields(staff_only=False)))),
                                                                                                              ['nn:1', 'c0:12', 'c1:13', 'c2:1', 's0:14', 's1:1', 'p0:1', 'p1:1', 'x0:1'], True, 'isOwner - ifnot: multi-arg, multi-obj.. Cancels out'),

            #IfFields
            (TestXAuthOwnedModel, (superuser, ifFields(value='typeA')),                  ['x0:12'], True, 'ifFields - single condition'),
            (TestXAuthOwnedModel, (superuser, ifFields(value='typeA', staff_only=True)), ['x0:1'],  True, 'ifFields - multi condition'),

            #ExcludeFields
            (TestXAuthOwnedModel, (anyone,    excludeFields('a', 'b', ifnot=staff), ),                                           ['nn^cd', 'c0^cd', 'c1^cd', 'c2^cd', 's0', 's1', 'p0', 'p1', 'x0'],  True, 'excludeFields - combined'),
            (TestXAuthOwnedModel, (superuser, excludeFields('a', 'b', ifnot=(ifFields(staff_only=False), ))),                    ['x0:1^cd23^cd4^cd'],                                       True, 'excludeFields - basics'),
            (TestXAuthOwnedModel, (superuser, excludeFields('a', 'b', ifnot=ifFields(staff_only=False)), excludeFields('c')),    ['x0:1^d2^abd3^d4^d'],                                      True, 'excludeFields - exclude + exclude'),


            #OnlyFields
            (TestXAuthOwnedModel, (anyone,    onlyFields('a', 'b', ifnot=staff), ),                                             ['nn^ab', 'c0^ab', 'c1^ab', 'c2^ab', 's0', 's1', 'p0', 'p1', 'x0'],   True, 'onlyFields - combined'),
            (TestXAuthOwnedModel, (superuser, onlyFields('a', 'b', ifnot=(ifFields(staff_only=False), ))),                      ['x0:1^ab23^ab4^ab'],                                        True, 'onlyFields - basics'),
            (TestXAuthOwnedModel, (superuser, onlyFields('a', 'b', ifnot=ifFields(staff_only=False)), excludeFields('a')),      ['x0:1^b2^bcd3^b4^b'],                                       True, 'onlyFields - only + exclude'),

            #NeverProduction
            execEnv(execEnvOverride=ExecEnv.local),
            (TestXAuthOwnedModel, (anyone, neverProduction, ),                              ['nn', 'c0', 'c1', 'c2', 's0', 's1', 'p0', 'p1', 'x0'],                     False, 'neverproduction ok in dev'),

            execEnv(execEnvOverride=ExecEnv.k8s),
            (TestXAuthOwnedModel, (anyone, neverProduction, ),                              [],                                                                         False, 'neverproduction not ok on prod'),

            execEnv(execEnvOverride=ExecEnv.docker),
            (TestXAuthOwnedModel, (anyone, neverProduction, ),                              ['nn', 'c0', 'c1', 'c2', 's0', 's1', 'p0', 'p1', 'x0'],                     False, 'neverproduction ok on docker'),

            #OnlyTest
            execEnv(execContextOverride=ExecContext.web),
            (TestXAuthOwnedModel, (anyone, onlyTest, ),                                     [],                                                                         False, 'onlytest not ok on web'),

            execEnv(execContextOverride=ExecContext.test),
            (TestXAuthOwnedModel, (anyone, onlyTest, ),                                     ['nn', 'c0', 'c1', 'c2', 's0', 's1', 'p0', 'p1', 'x0'],                     False, 'onlytest ok on test'),

            execEnvClear(),

            #OnlyDebug
            settings(DEBUG=True),
            (TestXAuthOwnedModel, (anyone, onlyDebug, ),                                    ['nn', 'c0', 'c1', 'c2', 's0', 's1', 'p0', 'p1', 'x0'],                     False, 'onlydebug ok in DEBUG'),

            settings(DEBUG=False),
            (TestXAuthOwnedModel, (anyone, onlyDebug ),                                     [],                                                                         False, 'onlydebug not ok in !DEBUG'),

            settingsClear(),

            #ELB check
            excludeCheck(['no-request']), #Exclude access methods that don't take in request, as we then won't know the context
            headers({'host': '224.338.282.818', 'user-agent': 'ELB-HealthChecker/1.0'}),
            (TestXAuthOwnedModel, (elb, ),                                                 [],                                                                          False, 'ELB check - Correct user agent, Wrong IP'),
            headers({'host': '10.0.5.22', 'user-agent': 'ELB-HealthCheCKER/1.0'}),
            (TestXAuthOwnedModel, (elb, ),                                                 [],                                                                          False, 'ELB check - Correct IP, wrong user agent'),
            headers({'host': '10.0.1.22', 'user-agent': 'ELB-HealthChecker/1.0'}),
            (TestXAuthOwnedModel, (elb, ),                                                 ['nn', 'c0', 'c1', 'c2', 's0', 's1', 'p0', 'p1', 'x0'],                      False, 'ELB check - Correct IP, correct user agent'),
            headersClear(),

            excludeCheck(['request']), #Exclude access methods taking in request.. All will fail
            (TestXAuthOwnedModel, (elb, ),                                                 [],                                                                          False, 'ELB check - No access without request'),

            excludeCheck([]), #Reset for later tests

            #hasContext
            excludeCheck(['no-request']), #Exclude access methods that don't take in request, as we then won't know the context
            setContext(customAttr = 3),
            (TestXAuthOwnedModel, (anyone, hasContext('customAttr'), ),                            ['nn', 'c0', 'c1', 'c2', 's0', 's1', 'p0', 'p1', 'x0'],                     False, 'Has context. All ok'),
            (TestXAuthOwnedModel, (hasContext('customAttr'), ),                                     'Privilege check not done for view access-name',                           False, 'Must have priv check'),
            setContext(customAttr = None),
            (TestXAuthOwnedModel, (anyone, hasContext('customAttr'), ),                            [],                                                                         False, 'Context set, but null. No one gets it'),

            excludeCheck(['request']), #Exclude access methods taking in request.. All will fail
            setContext(customAttr = 3),
            (TestXAuthOwnedModel, (anyone, hasContext('customAttr'), ),                            [],                                                                         False, 'No request. No access'),
            setContext(customAttr = None),
            (TestXAuthOwnedModel, (anyone, hasContext('customAttr'), ),                            [],                                                                         False, 'Context set, but null. No one gets it'),

            excludeCheck([]), #Reset for later tests

            #feature (FeatureAccess)
            #(TestXAuthOwnedModel, (anyone, feature('_test-predefined'), ),                  [],                                                                         False, 'No one has feature access'),
            #(TestXAuthOwnedModel, (anyone, feature('_test-all'), ),                         ['c0', 'c1', 'c2', 's0', 's1', 'p0', 'p1', 'x0'],                           False, 'All users have access by default'),
            #setFeatureAccess(**{'_test-predefined': True}),
            #(TestXAuthOwnedModel, (anyone, feature('_test-predefined'), ),                  ['c0', 'c1', 'c2', 's0', 's1', 'p0', 'p1', 'x0'],                           False, 'Now all users has access here too. Great'),
            #setFeatureAccess(**{'_test-predefined': False}),
            #(TestXAuthOwnedModel, (anyone, feature('_test-predefined'), ),                  [],                                                                         False, 'Aaand blocked again'),


            #Ref
            extraPermissions(customPerm = (anyone, perm('test.view_testxauthownedmodel'))),
            (TestXAuthOwnedModel,  (ref('customPerm'), ),                                          ['p0', 'p1', 'x0'],                                                         False, 'Ref: Access permissions'),

            extraPermissions(customPerm = (anyone, isOwnerOrNoOwner('owner_id', 'user', ifnot=(staff, superuser)))),
            (TestXAuthOwnedModel, (ref('customPerm'), ),                                           ['nn:1', 'c0:12', 'c1:13', 'c2:1', 's0:14', 's1:1', 'p0:1', 'p1:1', 'x0'],  True, 'Ref: Object permissions'),

            extraPermissions(customPerm = (anyone, perm('test.view_testxauthownedmodel')), deepCustomPerm = (ref('customPerm'), )),
            (TestXAuthOwnedModel, (ref('deepCustomPerm'), ),                                       ['p0', 'p1', 'x0'],                                                         False, 'Multi-ref'),

            extraPermissions(),

            #And / Or
            (TestXAuthOwnedModel, (anyone, and_(perm('test.view_testxauthownedmodel'), perm('test.change_testxauthownedmodel'))), ['p1', 'x0'],                                                   False, 'And - access'),
            (TestXAuthOwnedModel, (anyone, or_(perm('test.view_testxauthownedmodel'), perm('test.change_testxauthownedmodel'))), ['p0', 'p1', 'x0'],                                              False, 'Or - access'),

            (TestXAuthOwnedModel, (anyone, and_(superuser, ifFields(value='typeA'), ifFields(staff_only=False))),      ['x0:2'],                                          True, 'And - object'),
            (TestXAuthOwnedModel, (anyone, and_(superuser, or_(ifFields(value='typeB'), ifFields(staff_only=False)))), ['x0:234'],                                         True, 'Or - object'),

        ]
        # fmt: on

        def logErrorStr(Obj, perms, expResult, comment, res, error):
            return f"Actual vs expected: {res} vs {expResult} on object {Obj.__name__} for {comment}"

        # Run through tests. Accumulate errors till the end
        ctrlSettingsOverride = {}
        ctrlExclude: list[str] = []
        ctrlExtraPermissions = {}

        results: list[Any] = []

        for Obj, perms, expResult, expHasObjCheck, comment in tests:
            if isinstance(Obj, str):
                p0 = perms

                if Obj == 'settings':
                    ctrlSettingsOverride.update(cast(dict, p0))
                elif Obj == 'settingsClear':
                    ctrlSettingsOverride = {}
                elif Obj == 'execEnv':
                    initExecEnv(**cast(dict, p0), ignoreSanityChecks=True)
                elif Obj == 'execEnvClear':
                    initExecEnv()
                elif Obj == 'context':
                    for r in requests:
                        for k, v in cast(dict, p0).items():  # pylint: disable=no-member
                            setattr(r, k, v)
                elif Obj == 'headers':
                    for r in requests:
                        for k, v in cast(dict, p0).items():
                            r.META[k] = v
                            r.headers[k] = v
                elif Obj == 'headersClear':
                    for r in requests:
                        r.META = {}
                        r.headers = {}
                # elif Obj == 'featureAccess':
                #    for u in users:
                #        for k, v in p0.items(): # pylint: disable=no-member
                #            if u is not None:
                #                FeatureAccess.updateAccess(u.id, k, v)
                elif Obj == 'exclude':
                    ctrlExclude = cast(list, p0)
                elif Obj == 'permissions':
                    ctrlExtraPermissions = cast(dict, p0)
                continue

            ctrlSettingsOverride['XAUTH_PERMISSIONS'] = {
                'access-name': perms,
                **TestAccess.OTHER_PERMS,
                **ctrlExtraPermissions,
            }

            with override_settings(**ctrlSettingsOverride):
                logger.info('==============================================================================')
                logger.info(f"= TEST {comment}")

                # Clear any cached data on request object
                for r in requests:
                    r.clearCachedData()

                # No guarantee for order unless ordered. Ensure ordered to simplify tests below
                querySet = Obj.objects.order_by('id')

                ############################################
                # Check if item has object check
                try:
                    hasObjCheck = containsObjectCheck('access-name')
                except PermissionException as e:
                    hasObjCheck = str(e)

                self.assertEqual(hasObjCheck, expHasObjCheck, comment)

                #############################################
                # Perform access check for all users
                accessUser: list[str] | str
                try:
                    accessUser = [
                        u.username if u else 'nn'
                        for u in users
                        if checkAccess('access-name', user=u if u else None, returnBool=True)
                    ]
                except PermissionException as e:
                    accessUser = str(e)

                # Perform same check with request as entry-point (assembled as it would be for graphql)
                accessReq: list[str] | str
                try:
                    accessReq = [
                        u.username if u else 'nn'
                        for u, r in zip(users, requests)
                        if checkAccess('access-name', request=r, returnBool=True)
                    ]
                except PermissionException as e:
                    accessReq = str(e)

                access_: list[str] | str
                try:
                    access_ = [
                        u.username if u else 'nn' for u, r in zip(users, requests) if _checkAccess(and_(*perms), u)
                    ]
                except PermissionException as e:
                    access_ = str(e)

                # Access method used for views. Returns HttpResponseRedirect on error
                accessView: list[str] | str
                try:
                    accessView = [
                        u.username if u else 'nn'
                        for u, r in zip(users, requests)
                        if viewAccess('access-name')(lambda *args, **kwargs: True)(r) is True
                    ]
                except PermissionException as e:
                    accessView = str(e)

                logger.info(f"checkAccess(user):   {accessUser}")
                logger.info(f"checkAccess(request): {accessReq}")
                logger.info(f"_checkAccess(user):  {access_}")
                logger.info(f"viewAccess(user):    {accessView}")

                ############################################
                # Perform object-level permission check, both with DB filters and with post-filters, with user and request. They should all match
                try:
                    annot = _objectAccessAnnotate(and_(*perms), Obj)
                    annotObjs = list(querySet.annotate(**annot).all())
                except PermissionException as e:
                    self.assertEqual(
                        str(e), hasObjCheck, comment
                    )  # Should only fail in certain cases, and then containsObjectCheck should have failed too
                    annotObjs = []

                offset = offsetByModel[Obj]

                objectsFilterUser: dict[str, list[int]] | str
                try:
                    objectsFilterUser = {
                        u.username if u else 'nn': [
                            obj.id - offset
                            for obj in applyObjectAccessFilter(querySet, 'access-name', Obj, user=u if u else None)
                        ]
                        for u in users
                    }
                except PermissionException as e:
                    objectsFilterUser = str(e)

                objectsFilterReq: dict[str, list[int]] | str
                try:
                    objectsFilterReq = {
                        u.username if u else 'nn': [
                            obj.id - offset for obj in applyObjectAccessFilter(querySet, 'access-name', Obj, request=r)
                        ]
                        for u, r in zip(users, requests)
                    }
                except PermissionException as e:
                    objectsFilterReq = str(e)

                objectsValidateUser: dict[str, list[int]] | str
                try:
                    objectsValidateUser = {
                        u.username if u else 'nn': [
                            obj.id - offset
                            for obj in objectAccessValidate(annotObjs, 'access-name', Obj, user=u if u else None)
                        ]
                        for u in users
                    }
                except PermissionException as e:
                    objectsValidateUser = str(e)

                objectsValidateReq: dict[str, list[int]] | str
                try:
                    objectsValidateReq = {
                        u.username if u else 'nn': [
                            obj.id - offset for obj in objectAccessValidate(annotObjs, 'access-name', Obj, request=r)
                        ]
                        for u, r in zip(users, requests)
                    }
                except PermissionException as e:
                    objectsValidateReq = str(e)

                objectsValidate_: dict[str, list[int]] | str
                try:
                    objectsValidate_ = {
                        u.username if u else 'nn': [
                            obj.id - offset for obj in annotObjs if _objectAccessValidation(obj, and_(*perms), u, Obj)
                        ]
                        for u in users
                    }
                except PermissionException as e:
                    objectsValidate_ = str(e)

                logger.info(f"objectAccessFilter(user):      {objectsFilterUser}")
                logger.info(f"objectAccessFilter(request):    {objectsFilterReq}")
                logger.info(f"objectAccessValidate(user):    {objectsValidateUser}")
                logger.info(f"objectAccessValidate(request):  {objectsValidateReq}")
                logger.info(f"_objectAccessValidation(user): {objectsValidate_}")

                if 'no-request' not in ctrlExclude:
                    accessRes = accessUser
                    objectsFilterRes = objectsFilterUser
                else:
                    accessRes = accessReq
                    objectsFilterRes = objectsFilterReq

                if 'no-request' not in ctrlExclude:
                    self.assertEqual(accessRes, accessUser, f"Consistency (1): {comment}")
                    if accessRes != 'Privilege check not done for view access-name':
                        self.assertEqual(
                            accessRes, access_, f"Consistency (2): {comment}"
                        )  # _checkAccess does not check for priv-check being present

                    self.assertEqual(
                        objectsFilterRes,
                        objectsFilterUser,
                        f"Consistency (3): {comment}",
                    )
                    if objectsFilterRes not in (
                        'AccessValueEquals cannot be used on models',
                        'Unknown Access Name `` in ref',
                    ):
                        self.assertEqual(
                            objectsFilterRes,
                            objectsValidateUser,
                            f"Consistency (4): {comment}",
                        )
                    if objectsFilterRes not in (
                        'Empty AccessOr not allowed',
                        'Empty AccessAnd not allowed',
                        'AccessValueEquals cannot be used on models',
                        'Unknown Access Name `` in ref',
                    ):
                        self.assertEqual(
                            objectsFilterRes,
                            objectsValidate_,
                            f"Consistency (6): {comment}",
                        )

                if 'request' not in ctrlExclude:
                    self.assertEqual(accessRes, accessView, f"Consistency (1): {comment}")
                    self.assertEqual(accessRes, accessReq, f"Consistency (1): {comment}")

                    self.assertEqual(
                        objectsFilterRes,
                        objectsFilterReq,
                        f"Consistency (3): {comment}",
                    )
                    if objectsFilterRes not in (
                        'AccessValueEquals cannot be used on models',
                        'Unknown Access Name `` in ref',
                    ):
                        self.assertEqual(
                            objectsFilterRes,
                            objectsValidateReq,
                            f"Consistency (5): {comment}",
                        )

                ###########################################
                # Field filters

                fields = ['a', 'b', 'c', 'd']
                try:
                    fieldFilters = getFieldFilters('access-name', fields)
                except PermissionConfigurationException as e:
                    # Error should be same as for checkUser (if any).. special case for field filters not implemented
                    if 'not implemented for NOT expression' not in str(e):
                        self.assertEqual(str(e), accessRes, comment)
                else:
                    # if not isinstance(fieldFilters, str):
                    fieldAccessUser = {
                        u.username if u else 'nn': {
                            obj.id
                            - offset: [
                                f
                                for f in fields
                                if f not in fieldFilters
                                or checkFieldFilters(
                                    fieldFilters[f],
                                    f,
                                    obj,
                                    'access-name',
                                    Obj,
                                    user=u if u else None,
                                    returnBool=True,
                                )
                            ]
                            for obj in annotObjs
                        }
                        for u in users
                    }
                    fieldAccessReq = {
                        u.username if u else 'nn': {
                            obj.id
                            - offset: [
                                f
                                for f in fields
                                if f not in fieldFilters
                                or checkFieldFilters(
                                    fieldFilters[f],
                                    f,
                                    obj,
                                    'access-name',
                                    Obj,
                                    request=r,
                                    returnBool=True,
                                )
                            ]
                            for obj in annotObjs
                        }
                        for u, r in zip(users, requests)
                    }

                    logger.info(f"fieldAccessUser(user):     {fieldAccessUser}")
                    logger.info(f"fieldAccessReq(request):    {fieldAccessReq}")

                    self.assertEqual(fieldAccessUser, fieldAccessReq, comment)

                fullLen = querySet.count()

                def accessRepr(
                    name,
                    fullLen=fullLen,
                    objectsFilterRes=objectsFilterRes,
                    fieldAccessUser=fieldAccessUser,
                ):
                    # Set length == 1 if all items in set are equal -> merged to one item
                    if (
                        len(objectsFilterRes[name]) == fullLen
                        and len({''.join(fs) for v, fs in fieldAccessUser[name].items()}) == 1
                    ):
                        # All objects are present, and field access is the same for each object
                        # pylint: disable-next=cell-var-from-loop
                        if any(len(fs) != len(fields) for v, fs in fieldAccessUser[name].items()):
                            # Not full access. Render access
                            fieldAccessList = ''.join(fieldAccessUser[name][objectsFilterRes[name][0]])
                            return f"{name}^{fieldAccessList}"
                        # Full access
                        return name

                    # Not access to all objects or unequal field access
                    reprVal = [
                        str(v)
                        # pylint: disable=cell-var-from-loop
                        + (
                            '^' + ''.join(fieldAccessUser[name][v])
                            if len(fieldAccessUser[name][v]) != len(fields)
                            else ''
                        )
                        # pylint: enable=cell-var-from-loop
                        for v in objectsFilterRes[name]
                    ]

                    objAccessList = ''.join(reprVal)
                    return f"{name}:{objAccessList}"

                # Check result. User is required to use both access and object-checks, so combine them for result
                res: list[str] | str
                if isinstance(accessRes, str):
                    res = accessRes
                else:
                    # Show object identifiers if all are not present or if they have different field visibility
                    res = [accessRepr(name) for name in accessRes]

                error = res != expResult

                results.append((Obj, perms, expResult, comment, res, error))

                if error:
                    logger.error(logErrorStr(*results[-1]))

        console = Console(record=True)
        table = Table()
        for col in ['Comment', 'Object', 'Result', 'Expected', 'Status']:
            table.add_column(col)

        for res in results:
            table.add_row(
                res[3],
                res[0].__name__,  # type: ignore[attr-defined]
                str(res[4]),
                str(res[2]),
                'ERROR' if res[5] else 'Ok!',
            )

        logger.info(f"Permissions Test Table\n{console.export_text()}")

        errorResults = [r for r in results if r[5]]
        if errorResults:
            errorStrings = [logErrorStr(*r) for r in errorResults]
            self.fail(msg='{} errors: \n{}'.format(len(errorResults), '\n'.join(errorStrings)))

    def test_errInput(self):
        """Verifies that access functions all fail if no rule is present for a given object"""
        user = createUser('c0', password='p1')
        obj = TestXAuthOwnedModel.objects.create(value='typeA')

        # Permissions not defined for object
        with self.assertRaisesRegex(PermissionException, 'Permissions not defined for `foobar`'):
            checkAccess('foobar')

        with self.assertRaisesRegex(PermissionException, 'Permissions not defined for `foobar`'):
            viewAccess('foobar')

        with self.assertRaisesRegex(PermissionException, 'Permissions not defined for `foobar`'):
            objectAccessFilter('foobar', TestXAuthParentModel)

        with self.assertRaisesRegex(PermissionException, 'Permissions not defined for `foobar`'):
            objectAccessValidate([], 'foobar', TestXAuthParentModel)

        with self.assertRaisesRegex(PermissionException, 'Permissions not defined for `foobar`'):
            getFieldFilters('foobar', ['1', '2'])

        with self.assertRaisesRegex(PermissionException, 'Permissions not defined for `foobar`'):
            checkFieldFilters([], 'x', [], 'foobar', TestXAuthParentModel)

        # Field filter on non-existing fields
        with override_settings(
            XAUTH_PERMISSIONS={
                'access-name': (excludeFields('xxxx'),),
                **TestAccess.OTHER_PERMS,
            }
        ):
            with self.assertRaisesRegex(
                PermissionException,
                'Exclusion placed on non-existing field xxxx on object access-name',
            ):
                getFieldFilters('access-name', ['value', 'owner', 'staff_only'])

        with override_settings(
            XAUTH_PERMISSIONS={
                'access-name': (onlyFields('xxxx'),),
                **TestAccess.OTHER_PERMS,
            }
        ):
            with self.assertRaisesRegex(
                PermissionException,
                '`Only` placed on non-existing field xxxx on object access-name',
            ):
                getFieldFilters('access-name', ['value', 'owner', 'staff_only'])

        # Condition on non-existing field
        with self.assertRaisesRegex(
            PermissionException,
            'AccessIfFieldValues failed: Model TestXAuthOwnedModel does not have field xxxx',
        ):
            ifFields(xxxx=10).checkObject(user, obj, TestXAuthOwnedModel)

        # Ownership on non-existing field or with incorrect type
        with self.assertRaisesRegex(
            PermissionException,
            'AccessIsOwner failed: Model TestXAuthOwnedModel does not have field xxxx',
        ):
            isOwner('xxxx', 'user').checkObject(user, obj, TestXAuthOwnedModel)

        with self.assertRaisesRegex(PermissionException, 'Invalid userIdField. Choose one of user, ...'):
            isOwner('owner_id', 'xxx').checkObject(user, obj, TestXAuthOwnedModel)

        with self.assertRaisesRegex(
            PermissionException,
            'AccessIsOwnerOrNoOwner failed: Model TestXAuthOwnedModel does not have field xxxx',
        ):
            isOwnerOrNoOwner('xxxx', 'user').checkObject(user, obj, TestXAuthOwnedModel)

        with self.assertRaisesRegex(PermissionException, 'Invalid userIdField. Choose one of user, ...'):
            isOwnerOrNoOwner('owner_id', 'xxx').checkObject(user, obj, TestXAuthOwnedModel)

    def test_accessEquals(self):
        u0 = createUser('c1', password='p1')
        u1 = createUser('s0', password='p1', is_staff=True)

        # Set auth backends
        u0.backend = 'xxx.auth.SHTokenBackend'  # Client login
        u1.backend = 'django.contrib.auth.backends.ModelBackend'  # Admin login

        # Simple value filter
        with override_settings(
            XAUTH_PERMISSIONS={
                'access-name': (anyone, equals(1, 2, 3)),
                **TestAccess.OTHER_PERMS,
            }
        ):
            # Same values for both
            self.assertEqual(objectAccessValidate([1, 2, 3, 4, 5], 'access-name', user=u0), [1, 2, 3])
            self.assertEqual(objectAccessValidate([1, 2, 3, 4, 5], 'access-name', user=u1), [1, 2, 3])

        # Complex filter, limiting values based on other stuff
        with override_settings(
            XAUTH_PERMISSIONS={
                'access-name': (or_(and_(anyone, equals(1, 2, 3)), and_(staff, equals(4, 5))),),
                **TestAccess.OTHER_PERMS,
            }
        ):
            # Staff will get superset
            self.assertEqual(objectAccessValidate([1, 2, 3, 4, 5], 'access-name', user=u0), [1, 2, 3])
            self.assertEqual(
                objectAccessValidate([1, 2, 3, 4, 5], 'access-name', user=u1),
                [1, 2, 3, 4, 5],
            )

    def test_preCustomerAndUnknowndLoggedInUser(self):
        # Important that precustomer only works for a new customer being created
        request = RequestFactory().get('/')
        request.session = {}

        with override_settings(
            XAUTH_PERMISSIONS={
                'access-preclient': (preclient,),
                'access-client': (client,),
                'access-staff': (staff,),
                'access-superuser': (superuser,),
                **TestAccess.OTHER_PERMS,
            }
        ):
            # Should fail
            with self.assertRaisesRegex(PermissionException, 'Permission denied'):
                checkAccess('access-preclient', request=request)
            with self.assertRaisesRegex(PermissionException, 'Permission denied'):
                checkAccess('access-client', request=request)
            with self.assertRaisesRegex(PermissionException, 'Permission denied'):
                checkAccess('access-staff', request=request)
            with self.assertRaisesRegex(PermissionException, 'Permission denied'):
                checkAccess('access-superuser', request=request)

            # Should fail.. could be attempt to use someone elses email
            request.session = {'pipeonboard_customerId': 1}
            with self.assertRaisesRegex(PermissionException, 'Permission denied'):
                checkAccess('access-preclient', request=request)
            with self.assertRaisesRegex(PermissionException, 'Permission denied'):
                checkAccess('access-client', request=request)
            with self.assertRaisesRegex(PermissionException, 'Permission denied'):
                checkAccess('access-staff', request=request)
            with self.assertRaisesRegex(PermissionException, 'Permission denied'):
                checkAccess('access-superuser', request=request)

            # #Should succeed
            # u = createUser()
            # request.session = {'pipeonboard_customerId': u.shcustomer.id,
            #                    'pipeonboard_customerCreateStatus': OnboardingPipeline.CustomerCreateStatus.WAIT_ACTIVATE.value}
            # checkAccess('access-preclient', request=request)

            # #Client is never satisfied by pre-client
            # with self.assertRaisesRegex(PermissionException, 'Permission denied'):
            #     checkAccess('access-client', request=request)
            # with self.assertRaisesRegex(PermissionException, 'Permission denied'):
            #     checkAccess('access-staff', request=request)
            # with self.assertRaisesRegex(PermissionException, 'Permission denied'):
            #     checkAccess('access-superuser', request=request)

            # Now check UnknownLoggedInUser.. Should only have access to 'client'
            du = UnknownLoggedInUser()
            with self.assertRaisesRegex(PermissionException, 'Permission denied'):
                checkAccess('access-preclient', user=du)
            checkAccess('access-client', user=du)
            with self.assertRaisesRegex(PermissionException, 'Permission denied'):
                checkAccess('access-staff', user=du)
            with self.assertRaisesRegex(PermissionException, 'Permission denied'):
                checkAccess('access-superuser', user=du)

    def test_assumeLoggedIn(self):
        # Verifies that we can check logged-in access for a user without user being logged in
        u = createUser(is_staff=True)

        # Staff requires login
        with override_settings(XAUTH_PERMISSIONS={'access-staff': (staff,), **TestAccess.OTHER_PERMS}):

            # No access when not logged in
            with self.assertRaisesRegex(PermissionException, 'Permission denied'):
                checkAccess('access-staff', u)

            # Should succeed
            with assumeAdminLoggedIn([u]):
                checkAccess('access-staff', u)

            # Verify no lingering effects after mod above
            with self.assertRaisesRegex(PermissionException, 'Permission denied'):
                checkAccess('access-staff', u)

    def test_getObjectAccessAttributes(self):

        # Staff requires login
        with override_settings(
            XAUTH_PERMISSIONS={
                'test1': not_(and_(isOwner(ifnot=ifFields(xx=3)), or_(perm('test.foo')))),
                **TestAccess.OTHER_PERMS,
            }
        ):

            self.assertEqual(set(objectAccessAttributes('test1', User)), {'id', 'xx'})
