# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~

"""Utilities for PostgreSQL backups"""

import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import sh

logger = logging.getLogger(__name__)


def _get_databases(host: str, port: int, username: str, password: Optional[str] = None) -> List[str]:
    """
    Get list of all non-template databases
    
    :param host: PostgreSQL host
    :param port: PostgreSQL port
    :param username: PostgreSQL username
    :param password: PostgreSQL password
    :return: List of database names
    """
    env = os.environ.copy()
    if password:
        env['PGPASSWORD'] = password
    
    try:
        result = sh.psql(
            f'--host={host}',
            f'--port={port}',
            f'--username={username}',
            '--tuples-only',
            '--no-align',
            '--command=SELECT datname FROM pg_database WHERE datistemplate = false;',
            _env=env,
            _capture=True
        )
        
        databases = [db.strip() for db in result.stdout.strip().split('\n') if db.strip()]
        logger.info(f"Found {len(databases)} databases: {', '.join(databases)}")
        return databases
        
    except sh.ErrorReturnCode as e:
        logger.error(f"Failed to get database list: {e}")
        raise


def _backup_database(
    database: str,
    host: str,
    port: int,
    username: str,
    backup_path: Path,
    timestamp: str,
    compress: bool,
    password: Optional[str] = None
) -> Optional[str]:
    """
    Backup a single database
    
    :param database: Database name to backup
    :param host: PostgreSQL host
    :param port: PostgreSQL port
    :param username: PostgreSQL username
    :param backup_path: Directory to store backup
    :param timestamp: Timestamp for filename
    :param compress: Whether to compress the backup
    :param password: PostgreSQL password
    :return: Path to backup file if successful, None otherwise
    """
    backup_filename = f"{database}_{timestamp}.sql"
    if compress:
        backup_filename += '.gz'
    
    backup_file_path = backup_path / backup_filename
    
    try:
        logger.info(f"Backing up database: {database}")
        
        # Build pg_dump command
        cmd_args = [
            f'--host={host}',
            f'--port={port}',
            f'--username={username}',
            '--verbose',
            '--clean',
            '--if-exists',
            '--create',
            '--no-owner',
            '--no-privileges',
            f'--dbname={database}'
        ]
        
        env = os.environ.copy()
        if password:
            env['PGPASSWORD'] = password
        
        if compress:
            # Pipe pg_dump directly to gzip
            logger.info(f"Compressing backup for {database}")
            sh.pg_dump(*cmd_args, _env=env, _piped=True) | sh.gzip('-9', _out=str(backup_file_path))
        else:
            # Execute backup directly to final location
            sh.pg_dump(*cmd_args, _env=env, _out=str(backup_file_path))
        
        logger.info(f"Successfully backed up {database} to {backup_file_path}")
        return str(backup_file_path)
        
    except sh.ErrorReturnCode as e:
        logger.error(f"Failed to backup database {database}: {e}")
        return None


def _backup_global_objects(
    host: str,
    port: int,
    username: str,
    backup_path: Path,
    timestamp: str,
    compress: bool,
    password: Optional[str] = None
) -> Optional[str]:
    """
    Backup global objects (users, roles, etc.)
    
    :param host: PostgreSQL host
    :param port: PostgreSQL port
    :param username: PostgreSQL username
    :param backup_path: Directory to store backup
    :param timestamp: Timestamp for filename
    :param compress: Whether to compress the backup
    :param password: PostgreSQL password
    :return: Path to backup file if successful, None otherwise
    """
    global_backup_filename = f"global_objects_{timestamp}.sql"
    if compress:
        global_backup_filename += '.gz'
    
    global_backup_path = backup_path / global_backup_filename
    
    try:
        logger.info("Backing up global objects (users, roles, etc.)")
        
        # Build pg_dumpall command
        cmd_args = [
            f'--host={host}',
            f'--port={port}',
            f'--username={username}',
            '--globals-only',
            '--verbose'
        ]
        
        env = os.environ.copy()
        if password:
            env['PGPASSWORD'] = password
        
        if compress:
            # Pipe pg_dumpall directly to gzip
            logger.info("Compressing global objects backup")
            sh.pg_dumpall(*cmd_args, _env=env, _piped=True) | sh.gzip('-9', _out=str(global_backup_path))
        else:
            # Execute backup directly to final location
            sh.pg_dumpall(*cmd_args, _env=env, _out=str(global_backup_path))
        
        logger.info(f"Successfully backed up global objects to {global_backup_path}")
        return str(global_backup_path)
        
    except sh.ErrorReturnCode as e:
        logger.error(f"Failed to backup global objects: {e}")
        return None


def postgres_backup(
    host: str = 'localhost',
    port: int = 5432,
    username: str = 'postgres',
    password: Optional[str] = None,
    backup_dir: str = './backups/postgres',
    compress: bool = True,
    **kwargs: Any
) -> Dict[str, str]:
    """
    Create PostgreSQL backup of all databases and user configuration
    
    :param host: PostgreSQL host
    :param port: PostgreSQL port
    :param username: PostgreSQL username
    :param password: PostgreSQL password
    :param backup_dir: Directory to store backups
    :param compress: Whether to compress backup files
    :return: Dictionary mapping database names to backup file paths
    """
    
    backup_path = Path(backup_dir)
    backup_path.mkdir(parents=True, exist_ok=True)
    
    timestamp = time.strftime('%Y%m%d_%H%M%S')
    backup_files: Dict[str, str] = {}
    
    # Get list of all databases
    databases = _get_databases(host, port, username, password)
    
    # Backup each database
    for database in databases:
        if database in ['postgres', 'template0', 'template1']:
            continue  # Skip system databases
        
        backup_file_path = _backup_database(
            database, host, port, username, backup_path, timestamp, compress, password
        )
        
        if backup_file_path:
            backup_files[database] = backup_file_path
    
    # Backup global objects
    global_backup_path = _backup_global_objects(
        host, port, username, backup_path, timestamp, compress, password
    )
    
    if global_backup_path:
        backup_files['global_objects'] = global_backup_path
    
    return backup_files


def postgres_restore(
    database: str,
    backup_file: str,
    host: str = 'localhost',
    port: int = 5432,
    username: str = 'postgres',
    password: Optional[str] = None,
    **kwargs: Any
) -> None:
    """
    Restore a PostgreSQL database from backup
    
    :param database: Target database name
    :param backup_file: Path to backup file
    :param host: PostgreSQL host
    :param port: PostgreSQL port
    :param username: PostgreSQL username
    :param password: PostgreSQL password
    """
    
    env = os.environ.copy()
    if password:
        env['PGPASSWORD'] = password
    
    try:
        logger.info(f"Restoring database {database} from {backup_file}")
        
        # Check if backup file is compressed
        is_compressed = backup_file.endswith('.gz')
        
        if is_compressed:
            # Use gunzip to decompress and pipe to psql
            sh.gunzip('-c', backup_file, _piped=True) | sh.psql(
                f'--host={host}',
                f'--port={port}',
                f'--username={username}',
                f'--dbname={database}',
                _env=env
            )
        else:
            # Direct restore
            sh.psql(
                f'--host={host}',
                f'--port={port}',
                f'--username={username}',
                f'--dbname={database}',
                '--file=' + backup_file,
                _env=env
            )
        
        logger.info(f"Successfully restored database {database}")
        
    except sh.ErrorReturnCode as e:
        logger.error(f"Failed to restore database {database}: {e}")
        raise


def postgres_restore_global_objects(
    backup_file: str,
    host: str = 'localhost',
    port: int = 5432,
    username: str = 'postgres',
    password: Optional[str] = None,
    **kwargs: Any
) -> None:
    """
    Restore global PostgreSQL objects (users, roles, etc.)
    
    :param backup_file: Path to global objects backup file
    :param host: PostgreSQL host
    :param port: PostgreSQL port
    :param username: PostgreSQL username
    :param password: PostgreSQL password
    """
    
    env = os.environ.copy()
    if password:
        env['PGPASSWORD'] = password
    
    try:
        logger.info(f"Restoring global objects from {backup_file}")
        
        # Check if backup file is compressed
        is_compressed = backup_file.endswith('.gz')
        
        if is_compressed:
            # Use gunzip to decompress and pipe to psql
            sh.gunzip('-c', backup_file, _piped=True) | sh.psql(
                f'--host={host}',
                f'--port={port}',
                f'--username={username}',
                _env=env
            )
        else:
            # Direct restore
            sh.psql(
                f'--host={host}',
                f'--port={port}',
                f'--username={username}',
                '--file=' + backup_file,
                _env=env
            )
        
        logger.info("Successfully restored global objects")
        
    except sh.ErrorReturnCode as e:
        logger.error(f"Failed to restore global objects: {e}")
        raise 