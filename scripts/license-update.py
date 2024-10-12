#!/usr/bin/env python3
# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~
# Update license headers for all source files including self and lint files

import glob
import os
import re

import click


def get_headers(use_apache=False):
    # Common excludes
    excludes = [
        '.*node_modules/.*',
        '.*ansible/library/gsetting.py',  # Separate Apache 2.0 license
        '.*olib/.*',  # Prevent updating licenses in olib from outside project
    ]

    # License text starts with Copyright and ends with ~ to make it easy to update later. Keep all old license texts in this
    # array to make updating old licenses easy

    license_apache = (
        'Licensed under the Apache License, Version 2.0 (the "License");\n'
        + 'Copyright 2024 Øivind Loe\n'
        + 'See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.\n'
        + '~\n'
    )

    license_private = (
        'Copyright (C) 2023 Øivind Loe - All Rights Reserved\n'
        'Unauthorized copying of this file, via any medium is strictly prohibited\n'
        'Proprietary and confidential\n'
        '~\n'
    )

    past_licenses: list[str] = []

    if use_apache:
        licenses = [license_apache, license_private, *past_licenses]
    else:
        licenses = [license_private, license_apache, *past_licenses]

    headers = [
        {
            'name': 'License.txt',
            'headers': licenses,
            'targets': ['license.txt'],
            'search': re.compile('.*'),
            'replace': lambda search, header, content: header,
        },
        {
            'name': 'PY Header',
            'headers': ['\n'.join([f"# {l}" if l else l for l in ll.split('\n')]) for ll in licenses],
            'targets': ['**/*.py', '**/*.sh'],
            'exclude': [*excludes],
            #'search': re.compile('^(#![^\n]*\n)?(.*)$', re.MULTILINE | re.DOTALL),
            'search': re.compile('^(#![^\n]*\n)?(.*)$', re.MULTILINE | re.DOTALL),
            'replace': lambda search, header, content: search.sub(rf"\1{header}\2", content, count=1),
        },
        {
            'name': 'JS Header',
            'headers': [
                '\n'.join(['/**', '\n'.join([f" * {l}" for l in ll.split('\n') if l]), ' **/\n']) for ll in licenses
            ],
            'targets': [
                '**/*.js',
                '**/*.jsx',
                '**/*.css',
                '**/*.scss',
                '**/*.c',
                '**/*.h',
                '**/*.cpp',
            ],
            'exclude': [*excludes],
            'search': re.compile('^(.*)$', re.MULTILINE | re.DOTALL),
            'replace': lambda search, header, content: search.sub(rf"{header}\1", content, count=1),
        },
    ]

    return headers


def updateFile(spec, filename, dryrun):
    with open(filename, encoding='utf-8') as f:
        content = f.read()

    # Any copyright statement in file?
    if 'Copyright' in content:
        # Find presence of any licenses
        found = False
        for i, l in enumerate(spec['headers']):
            if l in content:
                if i == 0:
                    # Current license present in file. All good
                    return 'CURRENT'

                # Old license
                if dryrun:
                    return f"OLD {i}"

                # Remove license from code. We could have replaced the license directly here, but by doing it
                # further down, we are more robust, as we can ensure that we insert the license in the right location
                content = content.replace(l, '')
                found = True
                break

        if not found:
            raise Exception(f'File `{filename}` has "Copyright" but no presence of a copyright header')

    if not dryrun:
        # Add new license
        content = spec['replace'](spec['search'], spec['headers'][0], content)

        # Write back content
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(content)

    return 'UPDATE'


totalMatches = 0
totalExcludes = 0
totalUpdated = 0
headerMatches = 0


def pathGenerator(spec, paths=None):
    """
    Call with targets to apply glob to find paths
    or call with paths to skip glob
    """
    global totalMatches, totalExcludes, headerMatches  # pylint: disable=global-statement

    print(spec['name'])
    excludeRegs = [re.compile(ex) for ex in spec.get('exclude', [])]

    if not paths:
        # Find paths from target glob
        for target in spec['targets']:
            print(f"  {target}")
            for path in glob.iglob(target, recursive=True):
                # Check excludes
                if any(ex.match(path) for ex in excludeRegs):
                    totalExcludes += 1
                    continue

                totalMatches += 1
                headerMatches += 1

                yield path

    else:
        for path in paths:
            # Make sure path matches targets
            for target in spec['targets']:
                targetRegex = target.replace('**/*', '.*')
                if re.match(f"^{targetRegex}$", path):
                    break
            else:
                # Not found
                continue

            # Check excludes
            if any(ex.match(path) for ex in excludeRegs):
                totalExcludes += 1
                continue

            totalMatches += 1
            headerMatches += 1

            yield path


@click.command()
@click.option('--dryrun/--no-dryrun')  # Disable dryrun to do stuff for real
@click.argument('paths', nargs=-1)
def main(paths, dryrun=False):
    global headerMatches, totalUpdated  # pylint: disable=global-statement

    # Olib is the only on using apache at this point. Expand later
    use_apache = os.path.exists('.is_olib')

    for spec in get_headers(use_apache):
        headerMatches = 0
        for path in pathGenerator(spec, paths=paths):
            status = updateFile(spec, path, dryrun)
            if status == 'UPDATE':
                totalUpdated += 1
            print(f"    {status:<8} {path}")

        if not paths and 'tgtCount' in spec and spec['tgtCount'] != headerMatches:
            raise Exception(f"expected {spec['tgtCount']} updates for {spec['name']}")

    print('SUMMARY')
    print(f"  updated:    {totalUpdated}")
    print(f"  of matches: {totalMatches}")
    print(f"  ignored:    {totalExcludes}")


if __name__ == '__main__':
    main()  # pylint: disable=no-value-for-parameter
