# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~
import re
from collections import defaultdict


def _split_env_files_content(env_contents: tuple[str, str]) -> dict[str, dict[str, str]]:

    grouped_vars = defaultdict(dict)
    errors = []

    for env_file, content in env_contents:
        current_group = None

        for line_ in content.splitlines():
            line = line_.strip()

            # print(f'line: {line}')

            if not line:
                continue

            # Match group headers like #[somename] and capture the name
            if line.startswith('#'):
                group_match = re.match(r'^#\[([\w\-\.]+)\]$', line)
                if group_match:
                    current_group = group_match.group(1)
                # print('  continue')
                continue

            try:
                key, value = line.split('=', 1)
                grouped_vars[current_group][key] = value
                # print(f'  values: {key}={value} for group {current_group}')
            except ValueError:
                errors.append(f'{env_file}: {line}')

    if errors:
        raise ValueError(f'Errors found in env files: {errors}')

    return grouped_vars


def split_env_files(env_files, output_prefix):
    """
    Given a list of env files, breaks them down into grouped sections, and outputs
    to files under the output_prefix with ".groupname" as suffixes

    Vars in later files or later in files take priority in case there are duplicates
    """

    contents = []
    for env_file in env_files:
        with open(env_file, encoding='utf-8') as f:
            contents.append((env_file, f.read()))

    grouped_vars = _split_env_files_content(contents)

    for group_name, group_vars in grouped_vars.items():
        output_file = f'{output_prefix}.{group_name}'
        with open(output_file, 'w', encoding='utf-8') as f:
            print(f'writing to {output_file}')
            for k, v in group_vars.items():
                f.write(f'{k}={v}\n')
