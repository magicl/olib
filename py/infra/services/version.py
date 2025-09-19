# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~
import datetime
import time

import semver
import sh


class VersionManager:
    """
    Manages version of a deployment as part of the build process.
    Requires initialization before use

    Release name is for name=foo
      - foo-1.8.0           -- for a prod release
      - foo-1.8.0-dev.NNN   -- for a dev release

    Only prod release tags are stored in GIT. Dev release tags increase the patch
    version of the last git-stored tag, and add a NNN suffix that is guaranteed to
    increase per release.

    Note: We configure ahead of time, but the work to initialize is done on demand
    because it may be done in different processes in case of parproc
    """

    def __init__(self) -> None:
        self.name = ''
        self.is_prod = False
        self.inc_type = ''
        self.tag_msg = ''

        self.configured = False
        self.initialized = False

        self._next_version_str = ''
        self._full_tag_msg = ''

    def configure(self, is_prod: bool, name: str = '', inc_type: str = 'patch', tag_msg: str | None = None) -> None:
        """
        Initialize the version manager.
        :param name: Name of the deployment
        """

        if self.configured:
            raise ValueError('Version manager already configured')

        if inc_type not in ['patch', 'minor', 'major']:
            raise ValueError(f'Invalid increment type: {self.inc_type}')

        self.name = name
        self.is_prod = is_prod
        self.inc_type = inc_type
        self.tag_msg = tag_msg or ''

        self.configured = True

    def commit(self) -> None:
        """
        Commit the version to git.
        """
        if not self.initialized:
            self._initialize()

        if self.is_prod:
            sh.git('tag', '-a', self._next_version_str, '-m', self._full_tag_msg)
            sh.git('push', 'origin', self._next_version_str)

    def get(self) -> str:
        """
        Get the current version.
        """
        if not self.initialized:
            self._initialize()

        return self._next_version_str

    def _initialize(self) -> None:
        if not self.configured:
            raise ValueError('Version manager not configured')

        self.initialized = True

        last_version = self._get_last_version_from_git()
        next_version = last_version

        if self.is_prod:
            next_version = next_version.next_version(part=self.inc_type)
        else:
            next_version = next_version.replace(prerelease=self._get_dev_version_suffix())

        if self.name:
            self._next_version_str = f'{self.name}-{next_version}'
        else:
            self._next_version_str = str(next_version)

        self._full_tag_msg = '\n'.join(
            [
                *([self.tag_msg] if self.tag_msg else []),
                f'Deployed: {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}',
            ]
        )

    def _get_last_version_from_git(self) -> semver.VersionInfo:
        """
        Fetch all git tags, filter by name prefix, and return the latest one sorted by semver.

        :return: The latest git tag with the name prefix, or None if no tags found
        """

        # Fetch all git tags
        all_tags = list(sh.git('--no-pager', 'tag', '--list', _iter=True))  # pylint: disable=unexpected-keyword-arg

        # Filter tags that start with the name prefix
        prefix = f"{self.name}-"
        matching_tags = [tag for tag in all_tags if tag.startswith(prefix)]

        if not matching_tags:
            return semver.Version.parse('0.0.0')

        # Find the latest version using linear search
        latest_version = None

        for tag in matching_tags:
            # Remove the prefix to get the version part
            version_part = tag[len(prefix) :]

            # Try to parse as semver using the semver package
            try:
                parsed_version = semver.Version.parse(version_part)

                # Compare with current latest version
                if latest_version is None or parsed_version > latest_version:
                    latest_version = parsed_version

            except ValueError:
                # Invalid version format, skip this tag
                continue

        if latest_version is None:
            return semver.Version.parse('0.0.0')

        return latest_version

    @staticmethod
    def _get_dev_version_suffix() -> str:
        """
        Creates a compressed timestamp that is strictly increasing in lexicographic order.
        Uses time.time(), converts to a custom base62 encoding that preserves ordering.
        """
        # Get current timestamp
        timestamp = time.time()
        timestamp_int = int(timestamp)

        # Use base62 encoding with custom character set that preserves lexicographic ordering
        # Characters: 0-9, A-Z, a-z (62 characters total)
        # This ensures that lexicographic comparison matches numeric comparison
        return VersionManager._encode_base62_ordered(timestamp_int)

    @staticmethod
    def _encode_base62_ordered(num: int) -> str:
        """
        Encode a number using base62 with a character set that preserves lexicographic ordering.
        Uses characters: 0-9, A-Z, a-z (62 characters total)
        This ensures that if num1 < num2, then encode(num1) < encode(num2) lexicographically.
        """
        if num == 0:
            return '0'

        # Character set: 0-9 (10), A-Z (26), a-z (26) = 62 characters
        # This ordering ensures lexicographic comparison matches numeric comparison
        chars = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'

        result = ''
        while num > 0:
            result = chars[num % 62] + result
            num //= 62

        # Pad with zeros to make it 8 characters long. More than we need, but let's be on the safe side.
        return result.zfill(8)
