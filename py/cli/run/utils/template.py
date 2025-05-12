# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~

import os

import click
from jinja2 import Environment, FileSystemLoader


def _render(
    ctx: click.Context, filename: str, out_filename: str, base_dir: str, extra_context: dict | None = None
) -> None:
    env = Environment(loader=FileSystemLoader(base_dir))  # nosec
    template = env.get_template(filename)
    with open(out_filename, 'w', encoding='utf-8') as f:
        f.write(template.render(ctx=ctx, meta=ctx.obj.meta, extra_context=extra_context, inst=ctx.obj.inst_or_none))


def render_template(
    ctx: click.Context, filename: str, extra_context: dict | None = None, suffix: str = '', base_dir: str | None = None
) -> str:
    """
    Applies template to target file, and returns a path to the new file to use. The new file is only updated if necessary
    :param suffix: Optional suffix to add to output filename to allow different output versions
    """
    out_filename = f".output/tmpl/{filename}{suffix}"
    missing = False

    if base_dir is None:
        base_dir = ctx.obj.meta.olib_path

    if not os.path.exists(out_filename):
        os.makedirs(os.path.dirname(out_filename), exist_ok=True)
        missing = True

    if missing or os.path.getmtime(f"{base_dir}/{filename}") > os.path.getmtime(out_filename):
        _render(ctx, filename, out_filename, base_dir, extra_context)

    return out_filename
