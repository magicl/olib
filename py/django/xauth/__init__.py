# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~


# from .primitives import (
#     AccessAnd,
#     AccessAnyoneAllowed,
#     AccessClientAllowed,
#     AccessDeny,
#     AccessExcludeFields,
#     AccessHasContext,
#     AccessIfFieldValues,
#     AccessIsOwner,
#     AccessIsOwnerOrNoOwner,
#     AccessNot,
#     AccessOnlyDebug,
#     AccessOnlyElasticLoadBalancer,
#     AccessOnlyFields,
#     AccessOnlyStaff,
#     AccessOnlySuperuser,
#     AccessOr,
#     AccessPass,
#     AccessPermissions,
#     AccessPreClientAllowed,
#     AccessRef,
#     AccessValueEquals,
#     UnknownLoggedInUser,
# )

# ok = AccessPass()
# anyone = AccessAnyoneAllowed()
# preclient = AccessPreClientAllowed()
# client = AccessClientAllowed()  # Logged in user
# staff = AccessOnlyStaff()
# superuser = AccessOnlySuperuser()
# elb = AccessOnlyElasticLoadBalancer()
# perm = AccessPermissions
# isOwnerOrNoOwner = AccessIsOwnerOrNoOwner
# isOwner = AccessIsOwner
# ifFields = AccessIfFieldValues
# excludeFields = AccessExcludeFields
# onlyFields = AccessOnlyFields
# # neverProduction = AccessNeverProduction()
# # onlyTest = AccessOnlyTest()
# onlyDebug = AccessOnlyDebug()
# hasContext = AccessHasContext
# or_ = AccessOr
# and_ = AccessAnd
# ref = AccessRef
# equals = AccessValueEquals  # Use to constrain non-model values
# not_ = AccessNot
# deny = AccessDeny()

# __all__ = [
#     'ok',
#     'anyone',
#     'preclient',
#     'client',
#     'staff',
#     'superuser',
#     'elb',
#     'perm',
#     'isOwnerOrNoOwner',
#     'isOwner',
#     'ifFields',
#     'excludeFields',
#     'onlyFields',
#     #'neverProduction',
#     #'onlyStage',
#     #'onlyTest',
#     'onlyDebug',
#     'hasContext',
#     'or_',
#     'and_',
#     'ref',
#     'equals',
#     'not_',
#     'deny',
#     'UnknownLoggedInUser',
#     'views',
# ]
