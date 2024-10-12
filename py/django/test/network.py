# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~

import threading

from olib.py.django.test.runner import get_test_thread_id

_next_port = 15000
_assigned_ports: dict[tuple[str, int], int] = {}
_lock = threading.Lock()


def get_test_port(service_name):
    """Allocates a port for the service on a given thread. If a port was already allocated, that one is returned"""
    global _next_port  # pylint: disable=global-statement

    key = (service_name, get_test_thread_id())

    if (port := _assigned_ports.get(key)) is not None:
        return port

    with _lock:
        port = _next_port
        _next_port += 1

    _assigned_ports[key] = port
    return port
