from django.core.management.commands.runserver import Command as RunserverCommand
from django.conf import settings

class Command(RunserverCommand):
    def on_bind(self, server_port):
        if getattr(settings, 'BACKEND_HOST', None) is None:
            super().on_bind(server_port)
        else:
            print(f"Starting development server at {settings.BACKEND_HOST}/")
