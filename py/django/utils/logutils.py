# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~

import logging
import os
import sys
from collections.abc import Callable
from typing import Any

from django.conf import settings


class Formatter(logging.Formatter):
    """Provides facilities to add request ID to log items from web requests and task ID for tasks"""

    # ANSI color codes
    COLORS = {
        'DEBUG': '\033[36m',  # Cyan
        'INFO': '\033[32m',  # Green
        'WARNING': '\033[33m',  # Yellow
        'ERROR': '\033[31m',  # Red
        'CRITICAL': '\033[35m',  # Magenta
        'RESET': '\033[0m',  # Reset
    }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        try:
            from celery._state import get_current_task

            self.getCurrentTask: Callable[[], Any] = get_current_task
        except ImportError:
            self.getCurrentTask = lambda: None

        from django_middleware_global_request import get_request

        self.getRequest = get_request
        self.notReprLog: bool | None = None
        self.parallelTest: bool | None = None
        self._use_colors: bool | None = None

    def _should_use_colors(self) -> bool:
        """Determine if colors should be used based on terminal capabilities"""
        # Check if we're in a terminal that supports colors
        if not hasattr(sys.stdout, 'isatty') or not sys.stdout.isatty():
            return False

        # Check environment variables that might disable colors
        if os.environ.get('NO_COLOR'):
            return False

        if os.environ.get('TERM') == 'dumb':
            return False

        # Check if FORCE_COLOR is set (for CI environments)
        if os.environ.get('FORCE_COLOR'):
            return True

        # Default to using colors in interactive terminals
        return True

    def format(self, record: logging.LogRecord) -> str:
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
            if self.notReprLog and hasattr(request, 'session'):
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

        # Get the base formatted message
        formatted = super().format(record)

        # Add colors if supported
        if self._use_colors is None:
            self._use_colors = self._should_use_colors()

        if self._use_colors:
            level_name = record.levelname
            color = self.COLORS.get(level_name, '')
            reset = self.COLORS['RESET']

            if color:
                # Colorize the level name in the formatted message
                formatted = formatted.replace(level_name, f"{color}{level_name}{reset}")

        return formatted
