#!/usr/bin/python3
# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~

import os
import shutil

from ansible.module_utils.basic import AnsibleModule

DOCUMENTATION = r"""
---
module: replace_with_symlink

short_description: Replaces target file with symlink to other file, backing up target file

options:
  target:
    description: File to replace with a symlink
    required: True
    type: str
  source:
    description: A link will be created to this file
    required: True
    type: str
  create_backup:
    description: Set to create backup of original file with suffix .bak
    required: False
    default: True
    type: bool
"""


def run_module() -> None:
    module_args = {
        'source': {'type': 'str', 'required': True},
        'target': {'type': 'str', 'required': True},
        'create_backup': {'type': 'bool', 'required': False, 'default': True},
    }

    result = {'changed': False, 'original_backed_up': False, 'symlink_created': False}

    module = AnsibleModule(argument_spec=module_args, supports_check_mode=True)

    target = os.path.abspath(os.path.expanduser(module.params['target']))
    source = os.path.abspath(os.path.expanduser(module.params['source']))
    create_backup = module.params['create_backup']

    if not os.path.exists(source):
        module.fail_json(msg=f"Source file does not exist: {source}")

    if os.path.exists(target):
        # Check if it is already a symlink
        if os.path.islink(target) and os.readlink(target) == source:
            result['changed'] = False
            module.exit_json(**result)
        else:
            if create_backup:
                # Backup the original file if not a symlink
                backup_file = target + '.bak'
                shutil.copy2(target, backup_file)
                result['original_backed_up'] = True

            # Remove the original file
            os.remove(target)

            result['changed'] = True

    # Create the symlink
    os.symlink(source, target)
    result['symlink_created'] = True
    result['changed'] = True

    module.exit_json(**result)


def main() -> None:
    run_module()


if __name__ == '__main__':
    main()
