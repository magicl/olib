# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~

import os
import sys
from importlib import import_module
from typing import Any

import django
from celery import Celery
from celery.exceptions import NotRegistered
from celery.security import disable_untrusted_serializers
from django.conf import settings
from kombu import Exchange, Queue

_noInitSendTask: Any = None


def _sendTaskInit(app: Any) -> Any:
    """
    Initial send_task function. Makes sure all tasks are imported, then replaces send_task with
    a quicker version, removing itself from the path
    """

    def handler(name: Any, args: Any = None, kwargs: Any = None, **opts: Any) -> Any:
        assert _noInitSendTask is not None, '_noInitSendTask must be set as part of pre-init'  # nosec: assert_used

        for m in app.conf.imports:
            import_module(m)

        app.send_task = _noInitSendTask
        return app.send_task(name, args or (), kwargs or {}, **opts)

    return handler


def _sendTaskEager(app: Any) -> Any:
    """Eager version of send_task(...) for use in development"""

    def handler(name: Any, args: Any = None, kwargs: Any = None, **opts: Any) -> Any:
        try:
            return app.tasks[name].apply_async(args or (), kwargs or {}, **opts)
        except NotRegistered as e:
            e.add_note(f"Available tasks: {', '.join(app.tasks)}")
            raise

    return handler


def initCelery(appName: Any) -> Any:
    """Initialize celery"""
    global _noInitSendTask  # pylint: disable=global-statement

    # If initialized as part of celery, init the django app
    if sys.argv[0].endswith('celery'):
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', f"{appName}.settings")
        django.setup()

    app = Celery(appName)

    # Configuration
    app.conf.task_serializer = 'pickle'
    app.conf.result_serializer = 'pickle'
    app.conf.accept_content = ['pickle']
    app.conf.result_accept_content = ['pickle']
    app.conf.worker_redirect_stdouts_level = 'INFO'
    app.conf.timezone = getattr(settings, 'TIME_ZONE', 'UTC')
    app.conf.task_create_missing_queues = False  # Better to be explicit about queues
    app.conf.task_always_eager = getattr(settings, 'CELERY_WORKERS_ALWAYS_EAGER', False)
    app.conf.broker_url = getattr(settings, 'CELERY_WORKERS_BROKER_URL', None)
    app.conf.result_backend = getattr(settings, 'CELERY_WORKERS_RESULT_BACKEND', None)
    app.conf.broker_connection_retry_on_startup = True

    app.conf.broker_transport_options = {
        'queue_order_strategy': 'priority',
        'global_keyprefix': getattr(settings, 'CACHE_PREFIX', ''),
    }

    disable_untrusted_serializers(whitelist=['json', 'pickle'])

    # NOTE: Pull in full setup
    # Exchange must have same name as queue due to redis limitations (does not support exchanges)
    app.conf.task_queues = (
        # #Initial scheduling queues
        # Queue('realtime',     exchange=Exchange('realtime',type='direct'),     routing_key='realtime'),
        # Queue('semirealtime', exchange=Exchange('semirealtime',type='direct'), routing_key='semirealtime'),
        # Queue('interactive',  exchange=Exchange('interactive',type='direct'),  routing_key='interactive'),
        # Queue('background',   exchange=Exchange('background',type='direct'),   routing_key='background'), #Items in background will be renamed
        # Queue('pool',         exchange=Exchange('pool',type='direct'),         routing_key='pool'),
        # #Some tasks are transformed into theses to distribute load properly
        # Queue('monster',      exchange=Exchange('monster',type='direct'),      routing_key='monster'),
        # Queue('heavy',        exchange=Exchange('heavy',type='direct'),        routing_key='heavy'),
        # Queue('medium',       exchange=Exchange('medium',type='direct'),       routing_key='medium'),
        # Queue('light',        exchange=Exchange('light',type='direct'),        routing_key='light'),
        # Queue('p-monster',    exchange=Exchange('p-monster',type='direct'),    routing_key='p-monster'),
        # Queue('p-heavy',      exchange=Exchange('p-heavy',type='direct'),      routing_key='p-heavy'),
        # Queue('p-medium',     exchange=Exchange('p-medium',type='direct'),     routing_key='p-medium'),
        # Queue('p-light',      exchange=Exchange('p-light',type='direct'),      routing_key='p-light'),
        # Not used actively, but is a fallback, and will be served
        Queue(
            'default',
            exchange=Exchange('default', type='direct'),
            routing_key='default',
        ),
    )

    # Provide the following as consts to avoid read-lookup to app.conf in celery.py, as it can lead to infinite recursion in some settings
    _CELERY_DEFAULT_TASK_QUEUE = 'default'  # Not a celery config
    _CELERY_DEFAULT_TASK_PRIORITY = 5  # Not a celery config

    app.conf.task_default_queue = _CELERY_DEFAULT_TASK_QUEUE
    app.conf.task_default_priority = _CELERY_DEFAULT_TASK_PRIORITY
    # app.conf.task_default_exchange_type = 'topic'
    app.conf.task_default_routing_key = _CELERY_DEFAULT_TASK_QUEUE
    app.conf.task_default_exchange = _CELERY_DEFAULT_TASK_QUEUE
    app.conf.task_create_missing_queues = False

    # Load task modules from all registered Django apps. Can only load from apps that have tasks, so must manually maintain
    # a list of apps that do. This code runs before app init, so apps don't have an ability to register themselves as having tasks
    app.conf.imports = [
        f"{appName}.tasks",
        *[f"{app}.tasks" for app in settings.INSTALLED_APPS if app in ('olib.py.django.celery_workers')],
    ]

    # Celery does not itself bypass send_task when eager.
    _noInitSendTask = _sendTaskEager(app) if app.conf.task_always_eager else app.send_task
    app.send_task = _sendTaskInit(app)  # type: ignore

    return app
