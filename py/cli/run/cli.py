# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~

import click


class GroupTopLevel(click.Group):
    """
    Splits commands and command groups into separate sections for help command
    """

    def format_commands(self, ctx, formatter):
        # Sort commands and groups
        commands = sorted(self.commands.items())
        cmds = []
        grps = []

        for name, cmd in commands:
            if isinstance(cmd, click.Group):
                grps.append((name, cmd))
            else:
                cmds.append((name, cmd))

        # Display commands
        if cmds:
            with formatter.section('Commands'):
                formatter.write_dl((name, cmd.get_short_help_str()) for name, cmd in cmds)

        # Display groups
        if grps:
            with formatter.section('Command Groups'):
                formatter.write_dl((name, cmd.get_short_help_str()) for name, cmd in grps)
