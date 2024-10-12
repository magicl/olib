# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~

import logging
import os
import tempfile
from typing import NamedTuple

import sh
from click.testing import CliRunner
from django.test import tag

from olib.py.cli.run.run import create_cli
from olib.py.cli.run.templates import remote
from olib.py.cli.run.utils.remote import RemoteHost, clear_sessions
from olib.py.django.conf.remote import conf_cli
from olib.py.django.test.cases import OTestCase
from olib.py.django.test.mock_server import MockMultiServer, mock_server_reset_all
from olib.py.django.test.network import get_test_port

logger = logging.getLogger(__name__)


class GQLReqResp(NamedTuple):
    auth: str | None
    query: str
    response: dict


class MockAppServer(MockMultiServer):
    """Server emulating app that remote is communicating with"""

    def __init__(self):
        self.reqresp: list[GQLReqResp] = []

        super().__init__(
            spec={
                'server': {
                    'localPort': get_test_port(f"{__name__}.MockAppServer"),
                    'handlers': [
                        (
                            r'GET /graphql',
                            'H',
                            lambda s, get, post, headers: s.gql(headers['X-Access-Token'], get),
                        ),
                        (
                            r'POST /graphql',
                            'H',
                            lambda s, get, post, headers: s.gql(headers['X-Access-Token'], post),
                        ),
                    ],
                }
            }
        )

    def gql(self, token, data):
        # Respond with matching req/resp or fail
        for rr in self.reqresp:
            if rr.query == data['query']:
                if rr.auth is not None and rr.auth != token:
                    raise Exception(f"Expected token {rr.auth} but got {token} for request {data}")

                return rr.response

        raise Exception(f"No response found for request {data}")


@tag('olib')
class TestCliRun(OTestCase):

    def tearDown(self):
        mock_server_reset_all()
        clear_sessions()

    def _check_cli_result(self, result, exp_code=None, exp_output=None):
        """Print exception in cli result if any"""
        # if result.exit_code and result.exc_info is not None:
        #    traceback.print_exception(*result.exc_info)
        #    self.fail('Exception in cli result')

        if exp_code is not None:
            self.assertEqual(result.exit_code, exp_code)

        if exp_output is not None:
            self.assertEqual(result.output, exp_output)

    def test_shell(self):
        """Smoke-test for shell. Verify that getting help message works"""
        ret = sh.python3('-m', 'olib.py.cli.run.run', '--help')
        self.assertTrue(ret.startswith('Usage: python -m olib.py.cli.run.run'))

    def test_help(self):
        """Smoke-test via click.testing. Verify that getting help message works"""
        cli = create_cli()
        runner = CliRunner()
        result = runner.invoke(cli, ['--help'])
        self.assertTrue(result.output.startswith('Usage: cli'))

    def test_auto_login(self):
        """Verifies automatic login with predefined credentials"""

        # Server setup
        server = MockAppServer.getSingletonServer(testName='test_auto_login')
        server_port = server.servers['server'].port
        server.reqresp = [
            GQLReqResp(
                None,
                'mutation { authTokenGet(username: "username", password: "password") { ... on AuthTokenResponse { token } ... on OperationInfo { messages { message } } } }',
                {'data': {'authTokenGet': {'token': 'magic'}}},
            ),
            GQLReqResp('magic', '{ hello }', {'data': {'hello': 'hey you!'}}),
        ]

        # Cli setup
        @remote(
            plugins=[conf_cli],
            hosts=[
                RemoteHost(
                    'local',
                    f"http://127.0.0.1:{server_port}",
                    try_creds=['username:password'],
                ),
            ],
        )
        class Config:
            pass

        # Run test
        cli = create_cli(config=Config)
        runner = CliRunner()
        result = runner.invoke(cli, ['remote', '-r', 'local', 'ping'], catch_exceptions=False)
        self._check_cli_result(result, 0, 'Trying credential-set 0\nhey you!\n')

    def test_manual_login(self):
        """Verifies manual login with predefined credentials"""

        # Server setup
        server = MockAppServer.getSingletonServer(testName='test_manual_login')
        server_port = server.servers['server'].port
        server.reqresp = [
            GQLReqResp(
                None,
                'mutation { authTokenGet(username: "username", password: "password") { ... on AuthTokenResponse { token } ... on OperationInfo { messages { message } } } }',
                {'data': {'authTokenGet': {'token': 'magic'}}},
            ),
            GQLReqResp('magic', '{ hello }', {'data': {'hello': 'hey you!'}}),
        ]

        # Temp file for login credentials
        token_file = tempfile.mkstemp(prefix='test_remote_tokens')[1]

        # Cli setup
        @remote(
            plugins=[conf_cli],
            hosts=[
                RemoteHost(
                    'local',
                    f"http://127.0.0.1:{server_port}",
                    try_creds=['username:password'],
                ),
            ],
            token_file_path=token_file,
        )
        class Config:
            pass

        # Run test
        cli = create_cli(config=Config)
        runner = CliRunner()

        result = runner.invoke(
            cli,
            ['remote', '-r', 'local', 'login'],
            input='username\npassword\n',
            catch_exceptions=False,
        )
        self._check_cli_result(result, 0, 'Your admin username:\nPassword: ')

        clear_sessions()

        result = runner.invoke(cli, ['remote', '-r', 'local', 'ping'], catch_exceptions=False)
        self._check_cli_result(result, 0, 'hey you!\n')

        clear_sessions()

        result = runner.invoke(cli, ['remote', '-r', 'local', 'logout'], catch_exceptions=False)
        self._check_cli_result(result, 0, 'Logged out\n')

        clear_sessions()

        result = runner.invoke(cli, ['remote', '-r', 'local', 'ping'], catch_exceptions=False)
        self._check_cli_result(result, 0, 'Trying credential-set 0\nhey you!\n')

        # Clean up temp file
        os.unlink(token_file)
