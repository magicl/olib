#!/usr/bin/python
"""
This lib is from https://raw.githubusercontent.com/jistr/ansible-gsetting/master/gsetting.py
See original license file in that repo. Apache 2.0 license.


ansible-gsetting
================

Ansible module for setting GSettings entries.

See also
[ansible-dconf](https://github.com/jistr/ansible-dconf).

Installation
------------

    curl https://raw.githubusercontent.com/jistr/ansible-gsetting/master/gsetting.py > ~/ansible_dir/library/gsetting

Usage examples
--------------

    # Embed the schema in the key
    - name: turn off hot corners
      gsetting:
        user: jistr
        key: org.gnome.desktop.interface.enable-hot-corners
        value: "{{'false'|string}}"

    # Specify the schema separately
    - name: turn off hot corners
      gsetting:
        user: jistr
        schema: org.gnome.desktop.interface
        key: enable-hot-corners
        value: "{{'false'|string}}"

    # Use a relocatable schema
    - name: set custom key binding
      gsetting:
        user: jistr
        schema: org.gnome.settings-daemon.plugins.media-keys.custom-keybinding
        path: /org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/custom0/
        settings:
          name: Flameshot
          binding: Print
          command: flameshot gui

    - name: do not remember mount password
      gsetting:
        user: jistr
        settings:
          org.gnome.shell.remember-mount-password: false
          org.gnome.desktop.wm.keybindings.panel-main-menu: "@as []"
          org.gnome.nautilus.preferences.default-folder-viewer: "'list-view'"

If you want to run Ansible as the user you want to adjust settings
for, you should omit the `user` parameter:

    - name: shortcut panel-main-menu
      gsetting:
        settings:
          org.gnome.desktop.wm.keybindings.panel-main-menu: "@as []"

Be careful with string values, which should be passed into GSetting
single-quoted. You'll need to quote the value twice in YAML:

    - name: nautilus use list view
      gsetting:
        user: jistr
        settings:
          org.gnome.nautilus.preferences.default-folder-viewer: "'list-view'"

    - name: nautilus list view columns
      gsetting:
        user: jistr
        settings:
          org.gnome.nautilus.list-view.default-visible-columns: "['name', 'size', 'date_modified', 'permissions', 'owner', 'group']"

"""


import re
import subprocess  # nosec
from os import environ

from ansible.module_utils.basic import AnsibleModule


class Setting:
    def __init__(self, schema: str | None, path: str | None, key: str) -> None:
        if not schema:
            schema, key = self.split_key(key)
        if path:
            if not path.endswith('/'):
                path += '/'
        arg1 = schema
        if path:
            arg1 += ':' + path
        self.args = (arg1, key)

    @staticmethod
    def split_key(full_key: str) -> tuple[str, str]:
        key_array = full_key.split('.')
        schema = '.'.join(key_array[0:-1])
        single_key = key_array[-1]
        return (schema, single_key)


def _check_output_strip(command: list[str]) -> str:
    return subprocess.check_output(command).decode('utf-8').strip()  # nosec


def _escape_single_quotes(string: str) -> str:
    return re.sub("'", r"'\''", string)


def _maybe_int(val: str) -> int | str:
    try:
        return int(val)
    except ValueError:
        return 0


def _get_gnome_version() -> tuple[int | str, ...] | None:
    try:
        return tuple(
            map(
                _maybe_int,
                (_check_output_strip(['gnome-shell', '--version']).split(' ')[2].split('.')),
            )
        )
    except FileNotFoundError:
        return None


def _get_gnome_session_pid(user: str) -> str | None:
    gnome_ver = _get_gnome_version()
    if gnome_ver and gnome_ver >= (42,):
        # It's actually gnome-session-binary, but pgrep uses /proc/#/status,
        # which truncates the process name at 15 characters.
        #
        # Note that this may _also_ work for GNOME 3.33.90, i.e., the code
        # block below, but I'm preserving that behavior because I don't have
        # earlier GNOME versions to check.
        #
        # Note also that the code block below won't work when the default
        # session named "gnome" isn't used. For example, in recent versions of
        # ubuntu the session name is "ubuntu", i.e., "session=ubuntu" rather
        # than "session=gnome".
        pgrep_cmd = ['pgrep', '-u', user, 'gnome-session-b']
    elif gnome_ver and gnome_ver >= (3, 33, 90):
        # From GNOME 3.33.90 session process has changed
        # https://github.com/GNOME/gnome-session/releases/tag/3.33.90
        pgrep_cmd = ['pgrep', '-u', user, '-f', 'session=gnome']
    else:
        pgrep_cmd = ['pgrep', '-u', user, 'gnome-session']

    try:
        # At least in GNOME 42, there are multiple gnome-session-binary
        # processes, and we only want the first one.
        lines = _check_output_strip(pgrep_cmd)
        return lines.split()[0]
    except subprocess.CalledProcessError:
        return None


def _get_phoc_session_pid(user: str) -> str | None:
    pgrep_cmd = ['pgrep', '-u', user, 'phoc']

    try:
        return _check_output_strip(pgrep_cmd)
    except subprocess.CalledProcessError:
        return None


def _get_dbus_bus_address(user: str | None) -> str | None:
    if user is None:
        if environ.get('DBUS_SESSION_BUS_ADDRESS') is None:
            return None

        return f"DBUS_SESSION_BUS_ADDRESS={environ['DBUS_SESSION_BUS_ADDRESS']}"

    pid = _get_gnome_session_pid(user) or _get_phoc_session_pid(user)
    if pid:
        return _check_output_strip(['grep', '-z', '^DBUS_SESSION_BUS_ADDRESS', f"/proc/{pid}/environ"]).strip('\0')

    return None


def _run_cmd_with_dbus(user: str | None, cmd: list[str], dbus_addr: str | None) -> str:
    if not dbus_addr:
        command = ['dbus-run-session', '--']
    else:
        command = ['export', dbus_addr, ';']
    command.extend(cmd)

    if user is None:
        return _check_output_strip(['/bin/sh', '-c', ' '.join(command)])

    return _check_output_strip(['su', '-', user, '-c', ' '.join(command)])


def _set_value(schemadir: str | None, user: str | None, setting: Setting, value: str, dbus_addr: str | None) -> str:
    command = ['/usr/bin/gsettings']
    if schemadir:
        command.extend(['--schemadir', schemadir])
    command.append('set')
    command.extend(setting.args)
    command.append(f"'{_escape_single_quotes(value)}'")

    return _run_cmd_with_dbus(user, command, dbus_addr)


def _get_value(schemadir: str | None, user: str | None, setting: Setting, dbus_addr: str | None) -> str:
    command = ['/usr/bin/gsettings']
    if schemadir:
        command.extend(['--schemadir', schemadir])
    command.append('get')
    command.extend(setting.args)

    return _run_cmd_with_dbus(user, command, dbus_addr)


def main() -> None:

    module = AnsibleModule(
        argument_spec={
            'state': {'choices': ['present'], 'default': 'present'},
            'user': {'default': None},
            'schemadir': {'required': False},
            'schema': {'required': False},
            'path': {'required': False},
            'key': {'required': False},
            'value': {'required': False},
            'settings': {'type': 'dict', 'required': False, 'default': {}},
        },
        supports_check_mode=True,
    )

    user = module.params['user']
    schemadir = module.params['schemadir']
    schema = module.params['schema']
    path = module.params['path']
    key = module.params['key']
    value = module.params['value']
    settings = module.params['settings']
    any_changed = False
    unchanged_settings = []
    changed_settings = []

    if key is None and len(settings) == 0:
        module.fail_json(msg='Either a key or a settings dict is required, ' 'neither was provided.')

    parsed_settings = []

    if key is not None:
        parsed_settings.append([Setting(schema, path, key), value])

    for key, value in settings.items():
        parsed_settings.append([Setting(schema, path, key), value])

    dbus_addr = _get_dbus_bus_address(user)

    for setting, value in parsed_settings:
        old_value = _get_value(schemadir, user, setting, dbus_addr)
        result = {'key': '.'.join(setting.args), 'value': old_value}
        changed = old_value != value
        any_changed = any_changed or changed

        if changed and not module.check_mode:
            _set_value(schemadir, user, setting, value, dbus_addr)
            result['new_value'] = value
            changed_settings.append(result)
        else:
            unchanged_settings.append(result)

    module.exit_json(
        **{
            'changed': any_changed,
            'unchanged_settings': unchanged_settings,
            'changed_settings': changed_settings,
        }
    )


if __name__ == '__main__':
    main()
