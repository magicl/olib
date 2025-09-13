# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~
import os
import re
from collections import defaultdict
from os import makedirs


def _split_env_files_content(env_contents: list[tuple[str, str]]) -> dict[str, dict[str, str]]:

    grouped_vars: dict[str, dict[str, str]] = defaultdict(dict)
    errors = []

    for env_file, content in env_contents:
        current_groups: list[str] | None = None

        for line_ in content.splitlines():
            line = line_.strip()

            # print(f'line: {line}')

            if not line:
                continue

            # Match group headers like #[somename] and capture the name
            if line.startswith('#'):
                group_match = re.match(r'^#\[([\w\-\.,]+)\]$', line)
                if group_match:
                    current_groups = group_match.group(1).split(',')
                # print('  continue')
                continue

            try:
                key, value = line.split('=', 1)

                if current_groups is None:
                    errors.append(f'No group found for {env_file}: {line}')
                    continue

                for group in current_groups:
                    grouped_vars[group][key] = value
                    # print(f'  values: {key}={value} for group {current_group}')
            except ValueError:
                errors.append(f'{env_file}: {line}')

    if errors:
        raise ValueError(f'Errors found in env files: {errors}')

    return grouped_vars


def split_env_files(env_files: list[str], output_prefix: str, substitutions: dict[str, str] | None = None) -> None:
    """
    Given a list of env files, breaks them down into grouped sections, and outputs
    to files under the output_prefix with ".groupname" as suffixes

    Vars in later files or later in files take priority in case there are duplicates

    @param substitutions: If any {key} is found in the env files, it will be replaced with the value

    env file example:

    [backend]
    FOO=bar

    [frontend]
    FOO=baz

    [frontend,frontend]
    FOO=qux

    """

    makedirs(os.path.dirname(output_prefix), exist_ok=True)

    contents = []
    for env_file in env_files:
        with open(env_file, encoding='utf-8') as f:
            content = f.read()

            if substitutions is not None:
                for key, value in substitutions.items():
                    content = content.replace(f'{{{key}}}', value)

            contents.append((env_file, content))

    grouped_vars = _split_env_files_content(contents)

    for group_name, group_vars in grouped_vars.items():
        output_file = f'{output_prefix}.{group_name}'
        with open(output_file, 'w', encoding='utf-8') as f:
            print(f'writing to {output_file}')
            for k, v in group_vars.items():
                f.write(f'{k}={v}\n')
