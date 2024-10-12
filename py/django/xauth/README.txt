# Intro

* Extends Django's permissions system with more configurable ABAC/RBAC schemes


# Settings

- XAUTH_EXPOSE_VERBOSE_ERRORS     - Whether to output verbose permission errors. Good on development, not on production. Defaults to settings.DEBUG
- XAUTH_EARLY_CHECKS_DISABLE      - Disable early checks for accessName validity when decorators are applied. Disable for e.g. speedups
- XAUTH_PERMISSIONS               - List of permissions
