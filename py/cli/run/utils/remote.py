# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~

import getpass
import json
import logging
import re
import sys
import time
from typing import NamedTuple

import click
import requests

from ....exceptions import UserError
from ....utils.secretsfile import SecretsFile

logger = logging.getLogger(__name__)


_remote_connections: dict[str, 'RemoteConnection'] = {}


class CLIError(Exception):
    pass


class CLIHostUnreachable(CLIError):
    pass


class CLINoTokenException(CLIError):
    pass


class CLIAuthException(CLIError):
    pass


class CLIHttpError(Exception):
    def __init__(self, string, status_code):
        super().__init__(string)
        self.status_code = status_code

    @staticmethod
    def create_from_response(response):
        if response.status_code != 200:
            return CLIHttpError(
                f"error response: {response.status_code}\n{response.text}",
                response.status_code,
            )

        contentType = response.headers['Content-Type']
        if (
            contentType in ('application/json', 'text/html', 'text/plain')
            and '<!DOCTYPE html>' in response.text
            and 'Django administration' in response.text
        ):
            # Login error. Try to log in again through wrapper function
            return CLIHttpError(
                f"error response: {response.status_code}\nHit login view",
                response.status_code,
            )

        # No exception necessary
        return None

    def is_http_auth_error(self):
        return (
            self.status_code == 401 and 'Authorization Required' in self.args[0]
        )  # pylint: disable=unsubscriptable-object


def con(ctx: click.Context) -> 'RemoteConnection':
    """Returns a cached connection for the given context"""
    target = ctx.obj.meta.remote_target
    hosts = ctx.obj.meta.remote_hosts

    if target not in _remote_connections:
        if target not in hosts:
            raise UserError(f'remote_target "{target}" not defined in hosts list in config.py')

        _remote_connections[target] = RemoteConnection(
            hosts[target], token_file_path=ctx.obj.meta.remote_token_file_path
        )

    return _remote_connections[target]


def clear_sessions():
    global _remote_connections  # pylint: disable=global-statement
    _remote_connections = {}


class RemoteHost(NamedTuple):
    name: str
    url: str
    try_creds: list[str] = (
        []
    )  # List of credentials to try for quick sign-in to dev environments with no sensitive data. Provide as ['user0:pwd0', 'user1:pwd1', ...]

    basic_auth: bool = False


class RemoteConnection:

    def __init__(
        self,
        host: RemoteHost,
        token_file_path: str,
        login_user: str | None = None,
        login_token: str | None = None,
        login_pwd: str | None = None,
        basic_auth_user: str = '',
        basic_auth_pwd: str = '',  # nosec: hardcoded_password_default
        interactive: bool = True,
    ):
        self.host = host

        self._login_user = login_user
        self._login_token = login_token
        self._login_pwd = login_pwd
        self._basic_auth_user = basic_auth_user
        self._basic_auth_pwd = basic_auth_pwd
        self._session = requests.Session()

        self._interactive = interactive

        self.secrets_file = SecretsFile(token_file_path)

    def token_save(self, retry=False):
        self._get_credentials(disable_cache=True, retry=retry)

        self.secrets_file.save_secret(
            self.host.url,
            json.dumps(
                [
                    self._login_user,
                    self._login_token,
                    self._basic_auth_user,
                    self._basic_auth_pwd,
                ]
            ),
        )

    def token_delete(self):
        deleted = self.secrets_file.delete_secret(self.host.url)

        # Delete current token if present
        if deleted:
            print('Logged out')
        else:
            print(self.host.url)
            print('Was not logged in')

    def token_list(self):
        print('Current logins:')
        for url in self.secrets_file.list_keys():
            print(f"  {url}")

    def token_clear_all(self):
        self.secrets_file.clear_secrets()

    def _getpass(self):
        if sys.stdin.isatty():
            return getpass.getpass()

        # During unit testing, getpass does not work
        print('Password: ', end='')
        return sys.stdin.readline().strip()

    def _get_credentials(
        self,
        disable_cache=False,
        retry=False,
        login_user=None,
        login_pwd=None,
        basic_auth_user=None,
        basic_auth_pwd=None,
        forceNonInteractive=False,
    ):
        """Gets authentication token for user"""
        if not disable_cache and self._login_pwd is None:
            # Try to pull from cache first
            secret = self.secrets_file.get_secret(self.host.url)
            if secret is not None:
                (
                    self._login_user,
                    self._login_token,
                    self._basic_auth_user,
                    self._basic_auth_pwd,
                ) = json.loads(secret)
                return

        login_user = login_user or self._login_user
        login_pwd = login_pwd or self._login_pwd

        basic_auth_user = basic_auth_user or self._basic_auth_user
        basic_auth_pwd = basic_auth_pwd or self._basic_auth_pwd

        if not (login_user or login_pwd) and (not self._interactive or forceNonInteractive):

            raise CLINoTokenException(
                'Configured as non-interactive, and username/pwd/token not provided for login to server'
            )

        while True:
            # If we get here, token file is not available. Ask for pwd
            if login_user is None:
                print('Your admin username:')
                login_user = sys.stdin.readline().strip()
                logger.debug(f"DEBUG: user + pwd.. user is: {login_user}")
                login_pwd = self._getpass()
                logger.debug(f"DEBUG: passwd is: {login_pwd}")
            elif login_pwd is None:
                logger.debug('DEBUG: MIssing pwd')
                login_pwd = self._getpass()

            if self.host.basic_auth and not basic_auth_user:
                print('Your HTTP basic auth username:')
                basic_auth_user = sys.stdin.readline().strip()
                logger.debug('DEBUG: auth pwd')
                basic_auth_pwd = self._getpass()

            # Request authentication token
            try:
                resp = self.gql_mut(
                    'authTokenGet',
                    extra_fields='... on AuthTokenResponse { token }',
                    username=login_user,
                    password=login_pwd,
                    _authenticate=False,
                )
                logger.debug(f"got resp: {resp}")

            except requests.exceptions.ConnectionError as e:
                raise CLIHostUnreachable(f"Could not reach address {self.host.url}") from e

            except CLIHttpError as e:
                if e.is_http_auth_error():
                    if forceNonInteractive:
                        # Bubble exception up
                        raise e

                    print('HTTP Basic Auth Error')

                    # Ask for a new http password
                    basic_auth_user = ''
                    # Loop around to try again

                else:
                    # Some other error
                    print(e)
                    if retry:
                        print('unable to log in...retrying')
                        time.sleep(3)
                        continue

                    raise CLIError(
                        f"Unable to authenticate with {self.host.url} for user {login_user} - error {e.status_code}"
                    ) from e

            else:
                # No HTTP error. Break to outter loop to continue connection attempts
                break

        self._login_user = login_user
        self._login_token = resp['authTokenGet']['token']
        self._basic_auth_user = basic_auth_user
        self._basic_auth_pwd = basic_auth_pwd
        logger.debug('GOT THE TOKEN')

    def _request(
        self,
        type,
        endpoint,
        *args,
        content_type='application/json',
        timeout=360000,
        _authenticate=True,
        **kwargs,
    ):
        args = (self.host.url + endpoint, *args)
        kwargs['headers'] = kwargs.get('headers', {}).copy()

        # Always do token-based authentication. Optionally add basic auth
        if _authenticate:
            kwargs['headers']['X-Access-Token'] = self._login_token

        if self.host.basic_auth:
            kwargs['headers']['Authorization'] = requests.auth._basic_auth_str(  # pylint: disable=protected-access
                self._basic_auth_user, self._basic_auth_pwd
            )

        kwargs['headers']['Content-type'] = content_type

        logger.debug(
            '{} {} auth: {}'.format(  # pylint: disable=consider-using-f-string
                type,
                endpoint,
                ', '.join((['Token'] if self._login_token else []) + (['HttpBasic'] if self.host.basic_auth else [])),
            )
        )

        # Make sure any files transmitted are rewound
        if 'files' in kwargs:
            for _, v in kwargs['files'].items():
                v[1].seek(0)

        try:
            if type == 'post':
                response = self._session.post(*args, timeout=timeout, **kwargs)
            elif type == 'get':
                response = self._session.get(*args, timeout=timeout, **kwargs)
            else:
                raise CLIError('invalid request type')
        except requests.exceptions.ConnectionError as e:
            raise CLIHostUnreachable(f"Could not reach address {endpoint}") from e

        http_exception = CLIHttpError.create_from_response(response)
        if http_exception is not None:
            raise http_exception  # pylint: disable=raising-bad-type

        if content_type == 'application/json':
            logger.debug(response.text)

            try:
                json_data = response.json()
            except Exception as e:
                raise CLIError(f"Invalid API return data: {response.text}") from e

            # for info in json_data.get('api-info', []):
            #     self.outputInfo(f'{info}')
            # for err in json_data.get('api-errors', []):
            #     print(f'ERROR: {err}')

            # if json_data.get('api-errors', []):
            #     raise CLIError('Errors encountered')

            return json_data
        return response

    def request(
        self,
        *args,
        _authenticate=True,
        _disable_auth_cache=False,
        _pass_http_exception=False,
        **kwargs,
    ):
        """Request wrapper that ensures authentication is taken care of"""

        def tryAuth():
            """Attempt authentication with remote server using pre-defined credentials first, then trying user credentials"""
            # When None is hit, user is asked for credentials
            try_creds = [*[v.split(':') for v in self.host.try_creds], None]

            for idx, creds in enumerate(try_creds):
                try:
                    if creds is not None:
                        # Try auto login
                        click.echo(f"Trying credential-set {idx}", err=True)
                        self._get_credentials(
                            disable_cache=True,
                            retry=False,
                            login_user=creds[0],
                            login_pwd=creds[1],
                            basic_auth_user=(creds[2] if len(creds) >= 4 else None),
                            basic_auth_pwd=(creds[3] if len(creds) >= 4 else None),
                        )
                    else:
                        # Manual login
                        click.echo(
                            f"Please enter credentials for server `{self.host.url}`",
                            err=True,
                        )
                        self._get_credentials(disable_cache=True, retry=True)
                    # If we get here, login was successful. Break and retry request
                    break
                except CLIHostUnreachable:
                    raise  # Pass through
                except CLIError:
                    if idx == len(try_creds) - 1:
                        # Just did last attempt. Still failing.. Pass failure through
                        raise
                    continue

        if self._login_token is None and _authenticate:
            # Try to fetch token without interaction
            try:
                self._get_credentials(disable_cache=_disable_auth_cache, forceNonInteractive=True)
            except CLIHttpError as e:
                if e.is_http_auth_error():
                    # No HTTP access. Need to get input from user
                    self._get_credentials(disable_cache=_disable_auth_cache)
                else:
                    # Other error.. Try to authenticate
                    tryAuth()
            except CLINoTokenException:
                # No auth token set up, but have HTTP access. Try to authenticate before proceeding. Will throw on error
                tryAuth()

        # On wrong token, Try the above credentials, then finally ask user to input again
        while True:
            try:
                return self._request(*args, _authenticate=_authenticate, **kwargs)
            except CLIHttpError as e:
                logger.debug('CLIHttpError')

                if _pass_http_exception or not _authenticate:
                    # Asked to pass exception on
                    raise
                # if e.is_http_auth_error():
                #    # No HTTP access. Need to get input from user
                #    self._getHttpPwd()
                if e.status_code == 401 or e.is_http_auth_error():
                    # Invalid token.. or http basic error
                    if self._login_token is not None:
                        # Already got a good token. Something else is wrong. Fail
                        raise CLIAuthException('Received token does not work on server!') from e

                    # Try  to log in with the provided credentials. If all fails, bail
                    tryAuth()
                else:
                    # Not auth error.. Pass it on
                    raise e

    @classmethod
    def _fmtGqlArg(cls, k, v, quoteString=True):
        if isinstance(k, str) and k.startswith('@'):
            # Enum. Strip @ from key, but don't quote value
            k = k[1:]
            quoteString = False

        if isinstance(v, str):
            # $ is Variable reference.. Pass through
            if v.startswith('$'):
                # Variable. Pass $ through for value
                pass
            elif quoteString:
                # String. Quote value. Also pass through json.dumps to quote it properly. json.dumps also
                # automatically adds double quotes
                v = json.dumps(v)

        elif isinstance(v, list):
            v = '[' + ','.join(cls._fmtGqlArg(k, val, quoteString)[1] for val in v) + ']'

        elif isinstance(v, dict):
            tups = [cls._fmtGqlArg(key, val, quoteString) for key, val in v.items()]
            v = '{' + ','.join(f"{key}: {val}" for key, val in tups) + '}'

        elif isinstance(v, bool):
            v = 'true' if v else 'false'

        else:
            v = str(v)

        return k, v

    def graphql(
        self,
        query,
        *args,
        raw_args=None,
        variables=None,
        waitProgress=False,
        _authenticate=True,
        **kwargs,
    ):
        """Helper function for graphql queries
        :param query: GrqphQL query. Start with 'mutation' if mutation
        :param raw_args: Optional dict of arguments for mutation. Use %% as placeholder in query. An argument with value None is excluded from mutation
        """
        mutation = query.startswith('mutation')
        variables = variables or {}
        mutName = None

        if mutation:
            # Find name of mutation if explicitly mentioned
            m = re.match(r'mutation\s[\s\w\(\$\):!]*\{\s*(\w+).*', query)
            if not m:
                raise Exception(f"Mutation GraphQL query not well formed. Not able to find mutation name: {query}")
            mutName = m.group(1)

        if '%%' in query:
            # Replace %% with raw_args
            values = []
            for k, v in raw_args.items():
                if v is not None:
                    k_, v_ = self._fmtGqlArg(k, v)
                    values.append(f"{k_}: {v_}")

            query = query.replace('%%', f"({', '.join(values)})" if values else '')

        logger.info(f"PRE-POST QUERY: {query}")

        resp = self.request(
            'post',  # if mutation else 'get',
            '/graphql',
            json={
                'query': query,
                **({'variables': variables} if variables is not None else {}),
            },
            _authenticate=_authenticate,
        )

        def printErrors(errors):
            print(f"GrqphQL:  {query}")
            print(f"Response: {resp}")
            for error in errors:
                print(f"  ERROR: {error}")
            raise CLIError('GraphQL errors encountered')

        #############################################
        # Handle errors

        # Check for GraphQL syntax errors
        if 'errors' in resp:
            printErrors([e['message'] for e in resp['errors']])

        # Query should always contain ok and errors
        if 'data' not in resp:
            printErrors(['"data" not in GraphQL response'])

        # Typical error outlet for query errors
        # if 'errors' in resp['data']:
        #    printErrors([e['message'] for e in resp['errors']])

        if mutation:
            if resp['data'][mutName] is None:
                printErrors(['Nothing returned from mutation. Does it not return anything? Must return at least cls()'])

            # if 'ok' not in resp['data'][mutName]:
            #    printErrors(['"ok" not in GraphQL response'])

            # if 'errors' not in resp['data'][mutName]:
            #    printErrors(['"errors" not in GraphQL response'])

            # API errors
            if (oi := resp['data'].get('OperationInfo')) is not None:
                printErrors([m['message'] for m in oi['messages']])

        ###########################################
        # Higher level functionality

        # if waitProgress:
        #    self._waitProgress(resp['data']['progressId'])

        return resp['data']

    def gql_query(self, query, raw_args=None):
        # Execute query
        resp = self.graphql(query, raw_args=raw_args)
        return resp
        # self._outputGqlData(resp, raw, printScope, onSuccess)
        # NOTE: Remove output call here, as well as onSuccess, ...

    def gql_mut(self, mutation, extra_fields='', _authenticate=True, **kwargs):
        query = 'mutation { ' + mutation + '%% { ' + extra_fields + ' ... on OperationInfo { messages { message } } } }'
        resp = self.graphql(
            query,
            raw_args={k: v for k, v in kwargs.items() if v is not None},
            _authenticate=_authenticate,
        )
        # self._outputGqlData(resp, raw, printScope, onSuccess)
        # NOTE: Remove output/printScope/++ call here, as well as onSuccess, ...
        return resp
