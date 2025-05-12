# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~

"""Utilities for mysql backups"""

import logging
import os
import re
import subprocess  # nosec
import sys
import tempfile
import time
import uuid
from collections import defaultdict, deque
from collections.abc import Callable
from pathlib import Path

import sh

logger = logging.getLogger(__name__)


def mysql_backup_import(
    create_pipe: Callable, database: str, filename: str, decrypt_pwd: str, debug_lookback: int = 128
) -> None:
    """
    Apply a mysql backup to a database

    :param create_pipe: function to create pipe to mysql shell (binary mode)
    :param filename:    compressed, encrypted sql (.gz.gpg) file to import
    :param decrypt_pwd: key for .gz.gpg file
    """

    def pass_pwd_to_pipe_thread(pwd, pipe):
        """Passes encryption PWD to gpg through pipe. Must be done in separate thread as 'sh' is blocking"""
        logger.info('Waiting to write to pipe')
        with open(pipe, 'w', encoding='utf-8') as fifo:
            fifo.write(pwd)
        logger.info('Wrote pwd to pipe')

    # Transformantions. Applies transformation of item[1] to any line that starts with item[0]
    transforms = [
        # (b'CREATE', lambda line, reg=re.compile(rb'^(CREATE DATABASE .*) `(\w+)` (.*)'): ''), #reg.sub(rb'\1 `%b` \3' % bDatabase, line)),
        # (b'USE',    lambda line, reg=re.compile(rb'^USE `(\w+)`'):                       ''), #reg.sub(rb'USE `%b`'   % bDatabase, line)),
        (b'CREATE DATABASE', lambda line: b''),
        (b'USE ', lambda line: b''),
        (b'--', lambda line: b''),
    ]

    re_insert = re.compile(rb'^INSERT INTO `(\w+)`.*')  # Regex for fetching name of insert
    try:
        # Pass pwd in fifo to avoid it being in 'ps aux'
        fifo_name = Path(tempfile.gettempdir()) / Path(
            next(tempfile._get_candidate_names())  # type: ignore[attr-defined] # pylint: disable=protected-access
        )  # Does not create the file

        # thread = threading.Thread(
        #     target=pass_pwd_to_pipe_thread, args=(decrypt_pwd + '\n', fifo_name)
        # )  # Start thread to write pwd to fifo
        # thread.start()
        pass_pwd_to_pipe_thread(decrypt_pwd + '\n', fifo_name)

        # Turn off logging and foreign key checks
        # with create_pipe() as pipe:
        #     pipe.put(b'''SET GLOBAL log_output = NONE;\n''')
        #     pipe.put(b'''SET GLOBAL max_allowed_packet = 512*1024*1024;\n''')
        #     pipe.put(b'''SET GLOBAL foreign_key_checks = 0;\n''')
        #     pipe.put(b'''SET GLOBAL connect_timeout = 28800;\n''')
        #     pipe.put(b'''SET GLOBAL autocommit = 0;\n''')
        #     pipe.put(b'''SET GLOBAL unique_checks = 0;\n''')

        filter_tables: list[str] = []

        # Track size of inserts in string-length
        insert_sizes: dict[str, int] = defaultdict(int)
        insert_begin_at = {}
        insert_end_at = {}

        dot_period = 100
        # pipe_time_seconds = 600

        # In the interest of speed, whole file is decrypted into memory before being decompressed
        cur_table = None
        line_i = 0
        debug_list: deque = deque(maxlen=debug_lookback)

        with subprocess.Popen(
            f"gpg --decrypt --batch --yes --passphrase-file {fifo_name} --cipher-algo AES256 -o- {filename} | gunzip",
            shell=True,  # nosec(subprocess_popen_with_shell_equals_true) # We control all input, so this is not a security issue
            stdout=subprocess.PIPE,
        ) as proc:
            assert proc.stdout is not None  # nosec: assert_used

            feed = iter(proc.stdout)
            line = None
            done = False

            while not done:
                # pipe_start_at = time.time()
                try:
                    with create_pipe() as (pipe, proc):
                        pipe.put(f"""USE {database};\n""".encode())
                        pipe.put(b"""SET GLOBAL max_allowed_packet = 512*1024*1024;\n""")
                        pipe.put(b"""SET GLOBAL connect_timeout = 28800;\n""")
                        pipe.put(b"""SET foreign_key_checks = 0;\n""")
                        # pipe.put(b'''SET autocommit = 0;\n''')
                        pipe.put(b"""SET unique_checks = 0;\n""")
                        # pipe.put(b'''SET GLOBAL log_output = NONE;\n''')

                        while True:

                            try:
                                if line is None:
                                    line = next(feed)

                                # Renames
                                for start, t in transforms:
                                    if line.startswith(start):
                                        line = t(line)

                                if not line:
                                    line = None
                                    continue

                                # Filter
                                m = re_insert.match(line)
                                if m:
                                    # Insert statement
                                    table_name = m.group(1).decode('utf-8')
                                    insert_sizes[table_name] += len(line)

                                    if table_name in filter_tables:
                                        line = None
                                        continue

                                    if table_name != cur_table:
                                        print(f"\nTABLE: {table_name}", end='')
                                        if cur_table:
                                            insert_end_at[cur_table] = time.time()
                                        insert_begin_at[table_name] = time.time()
                                        cur_table = table_name

                                    # # Most statemens are insert statements. When we see an insert statement, we know that the previous
                                    # # statement has been fully submitted to MySQL, and we can re-create the pipe if necessary
                                    # if time.time() - pipe_start_at > pipe_time_seconds:
                                    #     # Keep the line so it will be processed once the pipe has been recreated
                                    #     # pipe.put(b'''COMMIT''')
                                    #     print('!', end='')  # Indicate new pipe
                                    #     sys.stdout.flush()
                                    #     break

                                debug_list.append(line)

                                line_i += 1
                                if line_i % dot_period == 0:
                                    print('.', end='')
                                    sys.stdout.flush()

                                # Output data to mysql
                                pipe.put(line)
                                line = None

                                # if not proc.is_alive():
                                #     breakpoint()
                                #     print('check debug list.. anything off??')

                            except StopIteration:
                                # End of input
                                # pipe.put(b'''COMMIT''')
                                done = True
                                break

                except sh.ErrorReturnCode as e:
                    print(f"Error during import: {e.stderr}")

                    debug_filename = f"/tmp/mysql_backup_debug-{uuid.uuid4()}.sql"  # nosec
                    with open(debug_filename, 'w', encoding='utf-8') as f:
                        f.write('\n'.join([l.decode('utf-8') for l in debug_list]))

                    print(f"Debug output written to {debug_filename}")
                    raise e

            print('\nIMPORT DONE')

        # Clean up by resetting values. Use fixed values, as import might crash, and we would thus not be able to trust values
        # read in at the start of the next import
        with create_pipe() as (pipe, _):
            pipe.put(b"""SET GLOBAL max_allowed_packet = 64*1024*1024;\n""")
            pipe.put(b"""SET GLOBAL connect_timeout = 10;\n""")

        # Final table
        insert_end_at[cur_table] = time.time()

        # Output data for each
        print('INSERT sizes:')
        for k, v in sorted(insert_sizes.items(), key=lambda v: v[0]):
            size = round(v / 1024**2, 2)
            elapsed = round(insert_end_at[k] - insert_begin_at[k])
            size_str = '!!!' if size > 10000 else '!! ' if size > 5000 else '!  ' if size > 1000 else '   '
            table_name = k + ':'
            ignored_str = 'IGNORED' if k in filter_tables else ''
            print(f"  {table_name:<35} {size:> 8.1f} MB {size_str} {elapsed:>8.1f} s {ignored_str}")

    except:  # pylint: disable=bare-except
        logger.exception('issue loading backup')
    finally:
        if fifo_name is not None and os.path.exists(fifo_name):
            os.remove(fifo_name)
