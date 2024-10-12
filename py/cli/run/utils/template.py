# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~

import os

from jinja2 import Environment, FileSystemLoader


def _render(ctx, filename, out_filename, extra_context: dict | None = None):
    env = Environment(loader=FileSystemLoader(ctx.obj.meta.olib_path))  # nosec
    template = env.get_template(filename)
    with open(out_filename, 'w', encoding='utf-8') as f:
        f.write(template.render(ctx=ctx, meta=ctx.obj.meta, extra_context=extra_context))


def render_template(ctx, filename, extra_context: dict | None = None, suffix=''):
    """
    Applies template to targe file, and returns a path to the new file to use. The new file is only updated if necessary
    :param suffix: Optional suffix to add to output filename to allow different output versions
    """

    out_filename = f".output/tmpl/{filename}{suffix}"
    missing = False

    if not os.path.exists(out_filename):
        os.makedirs(os.path.dirname(out_filename), exist_ok=True)
        missing = True

    if missing or os.path.getmtime(f"{ctx.obj.meta.olib_path}/{filename}") > os.path.getmtime(out_filename):
        _render(ctx, filename, out_filename, extra_context)

    return out_filename
