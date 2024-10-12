# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~

import logging

from django.conf import settings


class Formatter(logging.Formatter):
    """Provides facilities to add request ID to log items from web requests and task ID for tasks"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            from celery._state import get_current_task

            self.getCurrentTask = get_current_task
        except ImportError:
            self.getCurrentTask = lambda: None

        from django_middleware_global_request import get_request

        self.getRequest = get_request
        self.notReprLog = None
        self.parallelTest = None

    def format(self, record):
        # If format called before full settings loaded, don't read settings, but read later
        if self.notReprLog is None and hasattr(settings, 'TEST_REPRODUCIBLE_LOG'):
            self.notReprLog = not settings.TEST_REPRODUCIBLE_LOG
            self.parallelTest = settings.TEST_PARALLEL

        if self.parallelTest:
            from olib.py.django.test.runner import get_test_thread_id

            record.__dict__['testThreadId'] = get_test_thread_id()

        request = self.getRequest()
        if request is not None:
            # Could do this more properly using: https://django-request-id.readthedocs.io/en/latest/
            if self.notReprLog:
                sessKey = request.session.session_key
                record.__dict__.update(
                    req_id=f"R{str(id(request))}",
                    sess_id=f"S{sessKey[-8:] if sessKey is not None else '?'}",
                )
            else:
                record.__dict__.update(
                    req_id='R-',
                    sess_id='S-',
                )

        else:
            record.__dict__.setdefault('req_id', '')
            record.__dict__.setdefault('sess_id', '')

            task = self.getCurrentTask()
            if task and task.request:
                record.__dict__.update(
                    task_id=task.request.id if self.notReprLog else '-',
                    task_name=task.name,
                )
            else:
                record.__dict__.setdefault('task_name', '')
                record.__dict__.setdefault('task_id', '')
        return super().format(record)
