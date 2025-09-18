# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~


from unittest.mock import patch

import semver

from olib.infra.services.version import VersionManager
from olib.py.django.test.cases import OTestCase


class TestVersionManager(OTestCase):
    """Test cases for VersionManager class"""

    def test_get_method_scenarios(self) -> None:
        """Test get() method with various initialization scenarios"""
        # Test cases: (is_prod, name, inc_type, last_version, dev_suffix, expected_result, description)
        test_cases = [
            # Before initialization - should raise error
            (None, None, None, None, None, ValueError, 'Before initialization'),
            # Dev release without name - patch increment
            (False, '', 'patch', '1.2.3', 'dev123', '1.2.3-dev123', 'Dev release without name - patch increment'),
            # Dev release with name - patch increment
            (
                False,
                'myapp',
                'patch',
                '1.2.3',
                'dev123',
                'myapp-1.2.3-dev123',
                'Dev release with name - patch increment',
            ),
            # Dev release with name - minor increment
            (
                False,
                'myapp',
                'minor',
                '1.2.3',
                'dev123',
                'myapp-1.2.3-dev123',
                'Dev release with name - minor increment',
            ),
            # Dev release with name - major increment
            (
                False,
                'myapp',
                'major',
                '1.2.3',
                'dev123',
                'myapp-1.2.3-dev123',
                'Dev release with name - major increment',
            ),
            # Production release with name
            (True, 'myapp', 'patch', '1.2.3', None, 'myapp-1.2.4', 'Production release with name'),
            # Production release without name
            (True, '', 'patch', '1.2.3', None, '1.2.4', 'Production release without name'),
            # Edge case: zero version
            (False, 'myapp', 'patch', '0.0.0', 'dev123', 'myapp-0.0.0-dev123', 'Zero version edge case'),
            # Edge case: large version
            (False, 'myapp', 'patch', '999.999.999', 'dev123', 'myapp-999.999.999-dev123', 'Large version edge case'),
            # Invalid increment type - should raise error
            (False, 'myapp', 'invalid', '1.2.3', None, ValueError, 'Invalid increment type'),
        ]

        for is_prod, name, inc_type, last_version, dev_suffix, expected_result, description in test_cases:
            with self.subTest(is_prod=is_prod, name=name, inc_type=inc_type, description=description):
                version_manager = VersionManager()

                if expected_result == ValueError:
                    if is_prod is None:
                        # Test that get() raises ValueError before initialization
                        with self.assertRaises(ValueError) as context:
                            version_manager.get()
                        self.assertIn('Version manager not configured', str(context.exception))
                    else:
                        # Test that initialize() raises ValueError for invalid increment type
                        with patch.object(version_manager, '_getLastVersionFromGit') as mock_git:
                            mock_git.return_value = (
                                semver.Version.parse(last_version) if last_version else semver.Version.parse('0.0.0')
                            )

                            with self.assertRaises(ValueError) as context:
                                version_manager.configure(
                                    is_prod=is_prod or False, name=name or '', inc_type=inc_type or 'patch'
                                )
                            self.assertIn('Invalid increment type', str(context.exception))
                else:
                    # Test normal functionality
                    with (
                        patch.object(version_manager, '_getLastVersionFromGit') as mock_git,
                        patch.object(version_manager, '_getDevVersionSuffix') as mock_suffix,
                    ):

                        mock_git.return_value = (
                            semver.Version.parse(last_version) if last_version else semver.Version.parse('0.0.0')
                        )
                        if dev_suffix:
                            mock_suffix.return_value = dev_suffix

                        version_manager.configure(
                            is_prod=is_prod or False, name=name or '', inc_type=inc_type or 'patch'
                        )
                        result = version_manager.get()

                        self.assertEqual(result, expected_result)
