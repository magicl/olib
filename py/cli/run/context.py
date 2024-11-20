# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~

import re
import sys
from typing import cast

import click

inst_defaults = {
    'env_files': [],
    'cluster': 'dev',
    'pck_registry': 'pck-reg.home.arpa',
}


class RunContext:
    def __init__(self, config, instName=None, clusterName=None):
        self.config = config

        # Resolve inst
        if config.insts is None:
            self._inst = None
        elif instName is None and clusterName is None:
            if len(config.insts) == 1:
                self._inst = config.insts[0]
            else:
                # Pick default
                sel = [c for c in config.insts if c.get('default') is True]
                if len(sel) > 1:
                    click.echo('Multiple inst configs with default set')
                    sys.exit(1)
                elif len(sel) == 1:
                    self._inst = sel[0]
                else:
                    self._inst = None
        else:
            # Pick by name or alias
            sel = [
                c
                for c in config.insts
                if (instName and (c.get('name') == instName or c.get('alias') == instName))
                or (clusterName and c.get('cluster') == clusterName)
            ]
            if len(sel) > 1:
                click.echo('Multiple matching insts')
                sys.exit(1)
            elif not sel:
                click.echo('No matching insts')
                sys.exit(1)
            else:
                self._inst = sel[0]

        if self._inst is not None:
            if not re.match(r'^[a-z\-]+$', self._inst['name']):
                click.echo('App name can only consist of lowercase letters and dashes')
                sys.exit(1)

            click.echo(f"inst: {self._inst['name']}\n----------------------", err=True)

            for k, v in inst_defaults.items():
                if k not in self._inst:
                    self._inst[k] = v

    @property
    def inst(self):
        if self._inst is None:
            click.echo('inst must be specified or defaulted to for this command')
            sys.exit(1)

        return cast(dict, self._inst)

    @property
    def inst_or_none(self):
        return self.inst if self._inst is not None else None

    @property
    def k8sContext(self):
        return self.inst['cluster']

    @property
    def k8sNamespace(self):
        return self.inst['name']

    @property
    def k8sAppName(self):
        return self.inst['name']

    @property
    def meta(self):
        return self.config.meta
