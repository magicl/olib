# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~

import glob
import os
import time
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from rich.console import Console
from rich.text import Text
from urllib3.exceptions import InsecureRequestWarning


def warm_cdn_cache_impl(
    base_url: str,
    max_age_seconds: int,
    glob_to_url_mappings: list[tuple[str, str]],
    max_workers: int = 10,
    timeout: int = 10,
    read_timeout: int = 30,
    verify_ssl: bool = False,
    max_attempts: int = 5,
    retry_delay_ms: int = 500,
) -> None:
    console = Console()

    # Suppress insecure request warnings
    warnings.filterwarnings('ignore', category=InsecureRequestWarning)

    print(f"Warming cache for {base_url}")

    cutoff_time = time.time() - max_age_seconds

    # Enumerate all files matching the globs
    files_to_fetch = []
    for glob_pattern, _ in glob_to_url_mappings:
        matching_files = glob.glob(glob_pattern, recursive=True)
        for file_path in matching_files:
            if not os.path.isfile(file_path):
                continue

            # Check if file was modified recently
            file_mtime = os.path.getmtime(file_path)
            if file_mtime <= cutoff_time:
                continue

            # Convert file path to URL path
            url_path = None
            for pattern, prefix in glob_to_url_mappings:
                if file_path.startswith(pattern.replace('**', '')):
                    # Remove the base directory and prepend the URL prefix
                    url_path = file_path.replace(pattern.replace('**', ''), prefix)
                    break

            if url_path is None:
                # Skip files that don't match expected patterns
                continue

            files_to_fetch.append((file_path, url_path))

    if not files_to_fetch:
        print('No recently modified files found to warm cache')
        return

    print(f"Found {len(files_to_fetch)} recently modified files to warm cache")

    # Calculate max URL length based on the longest URL
    max_url_length = max(len(f"{base_url}{url_path}") for _, url_path in files_to_fetch) + 10
    print(f"Max URL length: {max_url_length}")

    # Track results for each URL
    url_results = {}
    total_requests = 0
    successful_requests = 0

    def fetch_file_with_retries(file_info: tuple[str, str]) -> tuple[str, bool]:
        file_path, url_path = file_info
        full_url = f"{base_url}{url_path}"

        # Track attempts for this URL
        attempts = 0
        nonlocal total_requests, successful_requests

        for attempt in range(1, max_attempts + 1):
            attempts += 1
            total_requests += 1

            try:
                with warnings.catch_warnings():
                    warnings.simplefilter('ignore')
                    response = requests.get(full_url, timeout=(timeout, read_timeout), stream=True, verify=verify_ssl)
                # Consume the body so CDN finishes fetching from origin and can store it
                for _ in response.iter_content(chunk_size=64 * 1024):
                    pass

                success = 200 <= response.status_code < 300
                if success:
                    successful_requests += 1

                # Format URL for display
                display_url = full_url[:max_url_length] + ('...' if len(full_url) > max_url_length else '')

                if success:
                    # Extract caching information from headers
                    cache_info = ''
                    cache_control = response.headers.get('Cache-Control', '')
                    cf_status = response.headers.get('CF-Cache-Status', '')

                    if cache_control:
                        # Look for max-age in Cache-Control header
                        if 'max-age=' in cache_control:
                            import re

                            max_age_match = re.search(r'max-age=(\d+)', cache_control)
                            if max_age_match:
                                max_age_seconds = int(max_age_match.group(1))
                                if max_age_seconds >= 86400:  # 24 hours
                                    cache_info = f" (cache: {max_age_seconds // 86400}d"
                                elif max_age_seconds >= 3600:  # 1 hour
                                    cache_info = f" (cache: {max_age_seconds // 3600}h"
                                elif max_age_seconds >= 60:  # 1 minute
                                    cache_info = f" (cache: {max_age_seconds // 60}m"
                                else:
                                    cache_info = f" (cache: {max_age_seconds}s"

                                # Add CF cache status if available
                                if cf_status:
                                    cache_info += f", {cf_status}"
                                cache_info += ')'

                        elif 'no-cache' in cache_control or 'no-store' in cache_control:
                            cache_info = ' (no-cache'
                            if cf_status:
                                cache_info += f", {cf_status}"
                            cache_info += ')'
                    elif cf_status:
                        # No cache control header, but still show CF status if available
                        cache_info = f" (cache: unknown, {cf_status})"

                    status_text = Text(f"{response.status_code} ✅{cache_info}", style='green')
                    if attempt == 1:
                        console.print(f"{display_url:<{max_url_length}} {status_text}")
                    else:
                        console.print(f"{display_url:<{max_url_length}} {status_text} (attempt: {attempt})")
                    return file_path, True

                status_text = Text(f"{response.status_code} ❌", style='red')
                if attempt < max_attempts:
                    console.print(f"{display_url:<{max_url_length}} {status_text} (attempt: {attempt})")
                    time.sleep(retry_delay_ms / 1000.0)  # Convert ms to seconds
                else:
                    console.print(f"{display_url:<{max_url_length}} {status_text} (attempt {attempt}, failure)")

            except Exception as e:  # pylint: disable=broad-exception-caught
                # Format URL for display
                display_url = full_url[:max_url_length] + ('...' if len(full_url) > max_url_length else '')

                # Check for timeout errors
                error_msg = str(e)
                if 'timeout' in error_msg.lower() or 'timed out' in error_msg.lower():
                    error_display = 'TIMEOUT'
                else:
                    error_display = f"ERROR: {error_msg}"

                status_text = Text(f"{error_display} ❌", style='red')
                if attempt < max_attempts:
                    console.print(f"{display_url:<{max_url_length}} {status_text} (attempt: {attempt})")
                    time.sleep(retry_delay_ms / 1000.0)  # Convert ms to seconds
                else:
                    console.print(f"{display_url:<{max_url_length}} {status_text} (attempt {attempt}, failure)")

        return file_path, False

    # Use ThreadPoolExecutor to fetch files concurrently
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all fetch tasks
        future_to_file = {
            executor.submit(fetch_file_with_retries, file_info): file_info for file_info in files_to_fetch
        }

        # Process completed tasks
        for future in as_completed(future_to_file):
            file_path, success = future.result()
            url_results[file_path] = success

    # Calculate final statistics
    successful_fetches = sum(1 for success in url_results.values() if success)
    failed_fetches = len(url_results) - successful_fetches
    total_fetches = len(url_results)

    # Calculate rates
    request_success_rate = (successful_requests / total_requests * 100) if total_requests > 0 else 0
    final_success_rate = (successful_fetches / total_fetches * 100) if total_fetches > 0 else 0

    # List failed URLs
    failed_urls = [f"{base_url}{url_path}" for file_path, url_path in files_to_fetch if not url_results[file_path]]
    if failed_urls:
        print('\nFailed URLs:')
        for url in failed_urls:
            print(f"  - {url}")

    print('Cache warming complete:')
    print(f"  - Files prefetched: {total_fetches}")
    print(f"  - Successful (200): {successful_fetches}")
    print(f"  - Failed: {failed_fetches}")
    print(f"  - Request success rate: {request_success_rate:.1f}%")
    print(f"  - Final success rate: {final_success_rate:.1f}%")
