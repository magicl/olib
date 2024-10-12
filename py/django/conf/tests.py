# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~
import datetime

from django.test import tag
from django.utils import timezone
from freezegun import freeze_time

from olib.py.django.conf.models import OnlineSetting
from olib.py.django.conf.osettings import osettings
from olib.py.django.test.cases import OTestCase
from olib.py.exceptions import UserError


@tag('olib')
class Tests(OTestCase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.original_settings = {}

    def setUp(self):
        super().setUp()

        # Clear any settings.. Restore in tearDown
        self.original_settings = osettings.settings
        osettings.settings = {}

    def tear_down(self):
        osettings.settings = self.original_settings

        super().tearDown()

    def test_online_settings(self):
        osettings.register('strval', 'str', default='REF5', values=['REF5', 'REF15'])
        osettings.register('intval', 'int', default=200)
        osettings.register('floatval', 'float', default=1.0)

        now = timezone.now()

        with freeze_time(now):

            # Default values
            self.assertEqual(osettings.strval, 'REF5')
            self.assertEqual(osettings.intval, 200)

            # Direct write should not work
            with self.assertRaisesRegex(Exception, 'should not be modified like this'):
                osettings.intval = 200

            # Update values with erroneous inputs
            with self.assertRaisesRegex(UserError, 'length of setting'):
                osettings.write('strval', 'x' * (osettings.MAX_STR_LEN + 1))
            with self.assertRaisesRegex(UserError, 'int is required'):
                osettings.write('intval', 'abc')
            with self.assertRaisesRegex(UserError, 'one of the following values'):
                osettings.write('strval', 'xyz')

            self.assertEqual(OnlineSetting.objects.count(), 0)

            # Update with good values
            osettings.write('strval', 'REF15')
            osettings.write('intval', 399)

            self.assertEqual(OnlineSetting.objects.count(), 2)

            # Does not yet take effect (due to timeouts)
            self.assertEqual(osettings.strval, 'REF5')
            self.assertEqual(osettings.intval, 200)

        # Wait till timeouts done
        with freeze_time(now + datetime.timedelta(osettings.settings['strval'].cache_timeout_seconds * 60 + 1)):
            self.assertEqual(osettings.strval, 'REF15')
        with freeze_time(now + datetime.timedelta(osettings.settings['intval'].cache_timeout_seconds * 60 + 1)):
            self.assertEqual(osettings.intval, 399)

        # Verify OS getters
        self.assertEqual(str(osettings.ref('strval')), 'REF15')
        self.assertEqual(int(osettings.ref('intval')), 399)

        # Wrong types
        with self.assertRaisesRegex(Exception, 'is not an int'):
            int(osettings.ref('strval'))
        with self.assertRaisesRegex(Exception, 'is not a str'):
            str(osettings.ref('intval'))

        # Wrong name
        with self.assertRaisesRegex(Exception, 'does not exist'):
            int(osettings.ref('xyz'))

        # Test large int (> 32 bit)
        osettings.write('intval', 123456789987654321, invalidateCache=True)
        self.assertEqual(osettings.intval, 123456789987654321)

        # Test float value
        osettings.write('floatval', 3.1, invalidateCache=True)
        self.assertEqual(osettings.floatval, 3.1)

    def test_key_value(self):
        osettings.register('opt', 'key-str', default={})
        osettings.register('fopt', 'key-float', default={})
        osettings.register('iopt', 'key-int', default={})
        osettings.register('bopt', 'key-bool', default={})

        self.assertEqual(osettings.opt, {})

        # Write with string does not work
        with self.assertRaisesRegex(Exception, 'can only be written directly with a Dict'):
            osettings.write('opt', '')

        osettings.write('opt', {'k': 'a'}, invalidateCache=True)
        self.assertEqual(osettings.opt, {'k': 'a'})

        # Set keys
        osettings.set('opt', 'k', 'v', invalidateCache=True)
        self.assertEqual(osettings.opt, {'k': 'v'})

        osettings.set('opt', 'x', 'y', invalidateCache=True)
        self.assertEqual(osettings.opt, {'k': 'v', 'x': 'y'})

        osettings.set('opt', 'k', '2', invalidateCache=True)
        self.assertEqual(osettings.opt, {'k': '2', 'x': 'y'})

        # Del
        osettings.clr('opt', 'k', invalidateCache=True)
        self.assertEqual(osettings.opt, {'x': 'y'})

        with self.assertRaisesRegex(UserError, 'does not exist'):
            osettings.clr('opt', 'k', invalidateCache=True)

        osettings.clr('opt', 'x', invalidateCache=True)
        self.assertEqual(osettings.opt, {})

        # Other types
        osettings.write('iopt', {'a': 1, 'b': 2}, invalidateCache=True)
        osettings.set('iopt', 'a', 3, invalidateCache=True)
        self.assertEqual(osettings.iopt, {'a': 3, 'b': 2})

        osettings.write('fopt', {'a': 1.2, 'b': 2, 'c': 3, 'd': 4}, invalidateCache=True)
        osettings.set('fopt', 'b', 2.2, invalidateCache=True)
        osettings.set('fopt', 'e', 5, invalidateCache=True)
        self.assertEqual(osettings.fopt, {'a': 1.2, 'b': 2.2, 'c': 3, 'd': 4, 'e': 5})

        osettings.write('bopt', {'a': True, 'b': False}, invalidateCache=True)
        osettings.set('bopt', 'a', False, invalidateCache=True)
        self.assertEqual(osettings.bopt, {'a': False, 'b': False})

    def test_list_value(self):
        osettings.register('opt', 'list-str', default=['A', 'BB'])

        self.assertEqual(osettings.opt, ['A', 'BB'])

        # Write with string does not work
        with self.assertRaisesRegex(Exception, 'can only be written directly with a List'):
            osettings.write('opt', '')

        osettings.write('opt', ['A', 'ZZ'], invalidateCache=True)
        self.assertEqual(osettings.opt, ['A', 'ZZ'])

        # Set values
        osettings.add('opt', 'v', invalidateCache=True)
        self.assertEqual(osettings.opt, ['A', 'ZZ', 'v'])

        osettings.add('opt', 'y', invalidateCache=True)
        self.assertEqual(osettings.opt, ['A', 'ZZ', 'v', 'y'])

        # Del
        osettings.clr('opt', 'v', invalidateCache=True)
        self.assertEqual(osettings.opt, ['A', 'ZZ', 'y'])

        with self.assertRaisesRegex(UserError, 'does not exist'):
            osettings.clr('opt', 'k', invalidateCache=True)

        osettings.clr('opt', 'y', invalidateCache=True)
        self.assertEqual(osettings.opt, ['A', 'ZZ'])
