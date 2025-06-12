# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~

from olib.py.utils.execenv import isEnvProduction


def applyDjangoMigrationPatch():
    import django.db.backends.base.schema

    # pylint: disable=protected-access
    #################################################
    # FIX for weird migration issue in Django.
    # The original function below sometimes gets related_objects out of sync, and matches the wrong objects with eachother
    def _related_non_m2m_objects(old_field, new_field):
        from django.db.backends.base.schema import _is_relevant_relation  # type: ignore

        # Filter out m2m objects from reverse relations.
        # Return (old_relation, new_relation) tuples.

        oldFields = [obj for obj in old_field.model._meta.related_objects if _is_relevant_relation(obj, old_field)]
        newFields = [obj for obj in new_field.model._meta.related_objects if _is_relevant_relation(obj, new_field)]

        oldByKey = {f"{of.field.model._meta.model_name}.{of.field.name}": of for of in oldFields}
        newByKey = {f"{nf.field.model._meta.model_name}.{nf.field.name}": nf for nf in newFields}

        return [(oldByKey[k], newByKey[k]) for k in sorted(newByKey.keys()) if k in oldByKey]

        # Old implementation, assuming related_objects to be aligned.. they are not (for some reason)
        # return zip(
        #    (obj for obj in old_field.model._meta.related_objects if _is_relevant_relation(obj, old_field)),
        #    (obj for obj in new_field.model._meta.related_objects if _is_relevant_relation(obj, new_field))
        # )

    # Apply monkeypatch for django
    # earlyInfo('Applying monkeypatch for django migrations')
    django.db.backends.base.schema._related_non_m2m_objects = _related_non_m2m_objects  # type: ignore

    # pylint: enable=protected-access


def applyDjangoBanNPlusOne():
    """
    Prevents django from doing implicit db queries during attribute access. Still allowed on production
    Modified from: https://suor.github.io/blog/2023/03/26/ban-1-plus-n-in-django/
    """
    import logging

    from django.db.models.query_utils import DeferredAttribute

    logger = logging.getLogger(__name__)
    attrsSeen = set()
    isProduction = isEnvProduction()
    _DA_get_original = DeferredAttribute.__get__

    def _DeferredAttribute_get(self, instance, cls=None):
        nonlocal _DA_get_original

        if instance is None:
            return self
        data = instance.__dict__
        fieldName = self.field.attname

        # Normally this accessor won't be called if fieldName is in __dict__,
        # we need this part so that DeferredAttribute descendants with __set__ play nice.
        if fieldName in data:
            return data[fieldName]

        # Check if an excemption has been made
        # if not utils.sysglobals._allowAttrDbAccess:
        # If it's not there already then prevent an SQL query or at least notify we are doing smth bad
        attr = f"{instance.__class__.__name__}.{fieldName}"
        # Only trigger this check once per attr to not flood Sentry with identical messages
        if attr not in attrsSeen:
            attrsSeen.add(attr)
            message = f"Lazy fetching of {attr} may cause 1+N issue"
            # We stop in DEBUG mode and if inside tests but let production to proceed.
            # Using LookupError instead of AttributeError here to prevent higher level "handling" this.

            if isProduction:
                logger.exception(message)
            else:
                raise LookupError(message)

        # Proceed normally
        return _DA_get_original(self, instance, cls)

    DeferredAttribute.__get__ = _DeferredAttribute_get  # type: ignore


applyDjangoMigrationPatch()
applyDjangoBanNPlusOne()
