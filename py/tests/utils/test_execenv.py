# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~


from unittest.mock import patch

from django.test import tag

from olib.py.django.test.cases import OTestCase
from olib.py.utils.execenv import (
    ExecContext,
    ExecEnv,
    SanityCheckError,
    initExecEnv,
    isEnvProduction,
    isEnvTest,
)


@tag('olib')
class Tests(OTestCase):

    def test_environments(self):
        # Should currently be in test
        self.assertEqual(isEnvTest(), True)
        self.assertEqual(isEnvProduction(), False)

    def test_sanity_checks(self):
        # Disallow DEBUG=True on K8S
        with (
            patch('os.environ', {}),
            self.assertRaisesRegex(SanityCheckError, 'Running on k8s and DEBUG is not set to False'),
        ):
            initExecEnv(execEnvOverride=ExecEnv.k8s, execContextOverride=ExecContext.web)

        with (
            patch('os.environ', {'DEBUG': 'couldbetrue'}),
            self.assertRaisesRegex(SanityCheckError, 'Running on k8s and DEBUG is not set to False'),
        ):
            initExecEnv(execEnvOverride=ExecEnv.k8s, execContextOverride=ExecContext.web)

        with patch('os.environ', {'DEBUG': 'false'}):
            initExecEnv(execEnvOverride=ExecEnv.k8s, execContextOverride=ExecContext.web)

        # Disallow unknown/test on K8S
        with patch('os.environ', {'DEBUG': 'false'}):
            with self.assertRaisesRegex(
                SanityCheckError,
                'Running on k8s with "ExecContext.unknown" execution context',
            ):
                initExecEnv(execEnvOverride=ExecEnv.k8s, execContextOverride=ExecContext.unknown)

            with self.assertRaisesRegex(
                SanityCheckError,
                'Running on k8s with "ExecContext.test" execution context',
            ):
                initExecEnv(execEnvOverride=ExecEnv.k8s, execContextOverride=ExecContext.test)
