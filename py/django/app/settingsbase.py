# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~

"""
Good startingpoint for shared settings for django projects using OLIB
"""


import logging
import logging.config
import os
import sys
from typing import Any

import environ
from django.core.exceptions import ImproperlyConfigured

from olib.py.django.xauth.primitives import superuser
from olib.py.utils.args import testArg
from olib.py.utils.earlylogging import cliLogLevel, earlyInfo, fileLogLevel
from olib.py.utils.execenv import initExecEnv, isEnvLocal, isEnvTest

# Apply monkey patches
import olib.py.django.app.monkeypatches  # pylint: disable=unused-import # isort:skip

# Env variables
env = environ.FileAwareEnv()

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = os.getcwd()

# Dev vs Prod
DJANGO_ENV = env.str('DJANGO_ENV', default='development').lower()

if DJANGO_ENV == 'production':
    # In prod, env variables are loaded by kubernetes. Do not try to load additional env files
    DEBUG = False

else:
    # Load env files if present
    ENV_PATH = env.str('ENV_PATH', default='.')
    environ.Env.read_env(os.path.join(BASE_DIR, ENV_PATH, '.env'), overwrite=True)
    environ.Env.read_env(os.path.join(BASE_DIR, ENV_PATH, '.env.development'), overwrite=True)
    environ.Env.read_env(os.path.join(BASE_DIR, ENV_PATH, '.env.local'), overwrite=True)

    DEBUG = env.bool('DEBUG', default=True)


KB_POD_IP = env.str('KB_POD_IP', default='')
KB_POD_NAME = env.str('KB_POD_NAME', default='')
KB_POD_NS = env.str('KB_POD_NS', default='')

# Check execution environment after reading in env variables
initExecEnv()

###############################################################
# Logging
###############################################################

logLevelConsole = cliLogLevel()
logLevelLog = fileLogLevel()

# Extended logging enabled internally in modules. This adds significant time to test cases
LOG_DEBUG_ENABLED = logging.DEBUG in (logLevelConsole, logLevelLog)

LOGGING_CONFIG: None = None  # Disable django default logging config

LOGGING: dict[str, Any] = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        #'verbose': {
        #    '()': 'olib.py.django.utils.logutils.Formatter',
        #    'format': '[%(asctime)s] %(levelname)s [%(name)s:%(lineno)s] %(req_id)s/%(sess_id)s %(message)s',
        #    'datefmt': '%d/%b/%Y %H:%M:%S',
        # },
        'default': {
            '()': 'olib.py.django.utils.logutils.Formatter',
            'format': '%(levelname)s [%(name)s:%(lineno)s] %(req_id)s/%(sess_id)s %(message)s',
        },
    },
    'handlers': {
        'console': {
            'level': logLevelConsole,
            'class': 'logging.StreamHandler',
            'formatter': 'default',
            # The absl package, imported by tensorflow removes all StreamHandlers outputting to stderr. Get around
            # this by outputting to stdout
            'stream': sys.stdout,
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'DEBUG',
    },
    'loggers': {
        'environ.environ': {
            'level': 'INFO',  # At DEBUG, all settings are output to log
        },
        'django.utils.autoreload': {
            'level': 'INFO',  # At DEBUG, very noisy
        },
        'asyncio': {
            'level': 'INFO',  # At DEBUG, very noisy
        },
    },
}
# Configure logging
logging.config.dictConfig(LOGGING)


###########################################################
# Security
###########################################################

ALLOWED_HOSTS: list[str] = env.list('ALLOWED_HOSTS', default=['127.0.0.1'])
# Health checks come from the pod IP
if KB_POD_IP:
    ALLOWED_HOSTS.append(KB_POD_IP)

CSRF_TRUSTED_ORIGINS: list[str] = env.list('CSRF_TRUSTED_ORIGINS', default=['http://127.0.0.1'])
CORS_ALLOWED_ORIGINS: list[str] = env.list('CORS_ALLOWED_ORIGINS', default=['http://127.0.0.1'])

SECRET_KEY = env.str(
    'DJANGO_SECRET',
    default='django-insecure-)463jfd)6kqprxg&y7!-4m8x)o$9s=a)i-^0-^=_6l)6@whv*3',
)

# fmt: off
SESSION_COOKIE_HTTPONLY = True     #Make session cookie http-only, to prevent JS from sniffing it
SESSION_COOKIE_SECURE = not DEBUG  #Only serve session cookie over https
SESSION_COOKIE_SAMESITE = 'Strict'  #Maximum security - cookies only sent on same-site requests
CSRF_COOKIE_SECURE = not DEBUG     #Only serve csrf cookie over https
CSRF_COOKIE_SAMESITE = 'Strict'    #Maximum security - cookies only sent on same-site requests

CORS_ALLOW_CREDENTIALS = True      #Allow cookies to be sent with requests

SECURE_CONTENT_TYPE_NOSNIFF = True #Pevent browser from trying to guess content type
SECURE_BROWSER_XSS_FILTER = True   #Enable XSS protection header

SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_HSTS_SECONDS = 3600*24      #24 hours. Limits potential fallout, while still providing protection


# fmt: on

# Password validation
# https://docs.djangoproject.com/en/5.0/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

###########################################################
# Application definition
###########################################################

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'corsheaders',
    'olib.py.django.commands',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django_middleware_global_request.middleware.GlobalRequestMiddleware',  # Set up global request variable
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]


# Internationalization
# https://docs.djangoproject.com/en/5.0/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'America/Chicago'

USE_I18N = True

USE_TZ = True


# Don't automatically append slashes to urls. It can hide redirects
APPEND_SLASH = False


###############################################################
# Storage
# https://docs.djangoproject.com/en/5.0/ref/settings/#databases
###############################################################

# Defaults are applied to sqlite3
db_options: dict[str, Any] = {
    'CONN_MAX_AGE': 1000,  # Keep connection alive for a good amount of time
}

if env('MYSQL_URL', default=''):
    os.environ['_DB_URL'] = (
        env('MYSQL_URL')
        .replace('{MYSQL_USERNAME}', env('MYSQL_USERNAME', default=''))
        .replace('{MYSQL_PASSWORD}', env('MYSQL_PASSWORD', default=''))
        .replace('{MYSQL_DB}', env('MYSQL_DB', default=''))
    )

    db_options = {
        'CONN_MAX_AGE': 1000,  # Keep connection alive for a good amount of time
        'OPTIONS': {
            'charset': 'utf8mb4',
        },
    }

if env('POSTGRES_URL', default=''):
    os.environ['_DB_URL'] = (
        env('POSTGRES_URL')
        .replace('{POSTGRES_USERNAME}', env('POSTGRES_USERNAME', default=''))
        .replace('{POSTGRES_PASSWORD}', env('POSTGRES_PASSWORD', default=''))
        .replace('{POSTGRES_DB}', env('POSTGRES_DB', default=''))
    )

    db_options = {
        'OPTIONS': {
            'pool': True,
        }
    }

DATABASES = {
    'default': {
        **env.db_url('_DB_URL', default=f"sqlite:///{env('SQLITE_PATH', default=f'{BASE_DIR}/db.sqlite3')}"),
        'isolation_level': 'read committed',
        **db_options,
    }
}


if env('REDIS_URL', default=''):
    os.environ['REDIS_URL'] = (
        env('REDIS_URL')
        .replace('{REDIS_USERNAME}', env('REDIS_USERNAME', default=''))
        .replace('{REDIS_PASSWORD}', env('REDIS_PASSWORD', default=''))
    )
    if not env('REDIS_PREFIX'):
        raise ImproperlyConfigured('REDIS_PREFIX must be specified to avoid overlap with other apps')

CACHE_PREFIX = env.str('REDIS_PREFIX', default='')

CACHES = {
    'default': {
        **env.cache_url('REDIS_URL', default='locmemcache://'),
        'KEY_PREFIX': CACHE_PREFIX,
    }
}


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.0/howto/static-files/

STATIC_URL = 'static/'
STATIC_ROOT = env.str('STATIC_ROOT', default=os.path.join(BASE_DIR, '.output/static'))

MEDIA_URL = 'media/'
MEDIA_ROOT = env.str('MEDIA_ROOT', default=os.path.join(BASE_DIR, '.output/media'))


DEFAULT_FILE_STORAGE = (
    'django.core.files.storage.InMemoryStorage' if isEnvTest() else 'django.core.files.storage.FileSystemStorage'
)


# Default primary key field type
# https://docs.djangoproject.com/en/5.0/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


###############################################################
# Templates
###############################################################

# TEMPLATES = [
#     {
#         'BACKEND': 'django.template.backends.django.DjangoTemplates',
#         'DIRS': [],
#         'APP_DIRS': True,
#         'OPTIONS': {
#             'context_processors': [
#                 'django.template.context_processors.debug',
#                 'django.template.context_processors.request',
#                 'django.contrib.auth.context_processors.auth',
#                 'django.contrib.messages.context_processors.messages',
#             ],
#         },
#     },
# ]

TEMPLATES: list[dict[str, Any | dict[str, list[Any]]]] = [
    {  # DjangoTemplates are used for Admin system
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
            'loaders': [
                (
                    'django.template.loaders.filesystem.Loader',
                    [os.path.join(BASE_DIR, 'templates/overrides/')],
                ),
                'django.template.loaders.app_directories.Loader',
                #'admin_tools.template_loaders.Loader',
            ],
        },
        'NAME': 'django',
    },
]

# Add jinja2 template engine if jinja2 is installed
try:
    import jinja2  # pylint: disable=unused-import

    TEMPLATES.append(
        {
            'BACKEND': 'django.template.backends.jinja2.Jinja2',
            'DIRS': ['templates', 'olib/py/django/xauth/templates'],
            'APP_DIRS': True,
            'OPTIONS': {
                'environment': 'olib.py.django.app.jinja2env.environment',
            },
            'NAME': 'jinja2',
        }
    )
except ImportError:
    pass

# IMPORTANT: set option to make sure file urls in templates are replaced with filename.hash.ext


##############################################################
# App configuration
##############################################################

CELERY_WORKERS_BROKER_URL = env.str('REDIS_URL', default=None)
CELERY_WORKERS_RESULT_BACKEND = env.str('REDIS_URL', default=None)

if CELERY_WORKERS_BROKER_URL is None:
    CELERY_WORKERS_ALWAYS_EAGER = True  # No workers defined. Run work inline. This is used for local servers and tests


XAUTH_EXPOSE_VERBOSE_ERRORS = DEBUG or isEnvTest()

# Other settings groups
# fmt: off
XAUTH_PERMISSIONS = {
    'xauth__view_admins': superuser,
}
# fmt: on


# https://strawberry-graphql.github.io/strawberry-django/guide/settings/
STRAWBERRY_DJANGO = {
    'FIELD_DESCRIPTION_FROM_HELP_TEXT': True,
    'TYPE_DESCRIPTION_FROM_MODEL_DOCSTRING': True,
    'MUTATIONS_DEFAULT_ARGUMENT_NAME': 'input',
    'MUTATIONS_DEFAULT_HANDLE_ERRORS': True,
    'GENERATE_ENUMS_FROM_CHOICES': False,  # Recommended False
    'MAP_AUTO_ID_AS_GLOBAL_ID': True,
    'DEFAULT_PK_FIELD_NAME': 'id',
}


###############################################################
# Test Config
###############################################################

if isEnvTest():
    PASSWORD_HASHERS = ('django.contrib.auth.hashers.MD5PasswordHasher',)


# Special CLI args
_live = testArg({r'--live$': True})
_liveProd = testArg({r'--live-prod$': True})
_liveReduced = testArg({r'--live-reduced$': True})

TEST_LIVE = _live or _liveProd
TEST_LIVE_PROD = _liveProd
TEST_LIVE_REDUCED = _liveReduced or _liveProd
if TEST_LIVE:
    earlyInfo('Running selenium in live mode.')
    assert isEnvLocal(), 'Cannot currently selenium in live mode inside vagrant/docker.'  # nosec: assert_used

TEST_SELENIUM_GUI = testArg({r'--selenium-gui': True})
if TEST_SELENIUM_GUI:
    earlyInfo('Running selenium in non-headless mode. The driver viewport might have a minimum size.')
    assert isEnvLocal(), 'Cannot run selenium in gui mode inside vagrant/docker.'  # nosec: assert_used


# fmt: off
TEST_SELENIUM_GUI_DEVTOOLS    = testArg({r'--selenium-devtools': True})
TEST_SELENIUM_GUI_MAXIMIZED   = testArg({r'--selenium-maximized': True})
TEST_SELENIUM_DLY             = testArg({r'--selenium-dly=([0-9]*\.?[0-9]+)': lambda m: float(m.group(1)),
                                         r'--selenium-dly': 3})
TEST_SELENIUM_TIMEOUT_DISABLE = testArg({r'--selenium-timeouts-disable': True})

TEST_BREAK_ON_ERROR           = testArg({r'--break-on-error$': True})
TEST_DEBUG_MEM                = testArg({r'--debug-mem$': True})

TEST_REPRODUCIBLE_LOG         = testArg({r'--reproducible-log$': True})# Whether reproducible logs are enabled

TEST_RUN_FAILED               = testArg({r'--failed$': True}) #Run tests that failed in past iteration

TEST_UNSUPPRESS_LOG           = testArg({r'--unsuppress-log': True}) #Set to disable log suppression to see what is suppressed
TEST_DB_NAME_OVERRIDE         = testArg({r'--test-db=(\w+)': lambda m: m.group(1)})

TEST_PARALLEL                 = testArg({r'--test-db=(\d+)': lambda m: int(m.group(1)) > 1}, keep=True)
# fmt: on
