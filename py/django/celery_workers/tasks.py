# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~

from celery import shared_task


@shared_task(bind=True)
def debug_task(self) -> str:
    # print(f'Request: {self.request!r}')
    return 'hello from celery lib'
