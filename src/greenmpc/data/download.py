"""Safe standard-library downloader for public raw sources."""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class DownloadResult:
    url: str
    final_url: str
    local_path: Path
    byte_size: int
    sha256: str
    content_type: str | None
    content_length: str | None
    etag: str | None
    last_modified: str | None
    from_cache: bool


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_file(
    url: str,
    destination: Path,
    *,
    user_agent: str,
    timeout_seconds: int,
    retries: int,
    retry_backoff_seconds: int,
    temporary_suffix: str = ".part",
    force: bool = False,
    expected_format: str | None = None,
) -> DownloadResult:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and not force:
        _validate_cached_file(destination, expected_format)
        return DownloadResult(
            url=url,
            final_url=url,
            local_path=destination,
            byte_size=destination.stat().st_size,
            sha256=sha256_file(destination),
            content_type=None,
            content_length=None,
            etag=None,
            last_modified=None,
            from_cache=True,
        )

    part_path = destination.with_name(destination.name + temporary_suffix)
    attempts = retries + 1
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            if part_path.exists():
                part_path.unlink()
            return _download_once(
                url,
                destination,
                part_path,
                user_agent=user_agent,
                timeout_seconds=timeout_seconds,
                expected_format=expected_format,
            )
        except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
            last_error = exc
            if part_path.exists():
                part_path.unlink()
            if attempt >= attempts:
                break
            LOGGER.warning("Download failed for %s on attempt %s/%s: %s", url, attempt, attempts, exc)
            time.sleep(retry_backoff_seconds)
    raise RuntimeError(f"download failed for {url}: {last_error}") from last_error


def _download_once(
    url: str,
    destination: Path,
    part_path: Path,
    *,
    user_agent: str,
    timeout_seconds: int,
    expected_format: str | None,
) -> DownloadResult:
    request = Request(url, headers={"User-Agent": user_agent})
    with urlopen(request, timeout=timeout_seconds) as response:
        headers = response.headers
        content_type = headers.get("Content-Type")
        content_length = headers.get("Content-Length")
        final_url = response.geturl()
        bytes_written = 0
        next_progress = 50 * 1024 * 1024
        with part_path.open("wb") as handle:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                handle.write(chunk)
                bytes_written += len(chunk)
                if bytes_written >= next_progress:
                    LOGGER.info("Downloaded %.1f MB from %s", bytes_written / 1_000_000, url)
                    next_progress += 50 * 1024 * 1024

    if bytes_written == 0:
        raise ValueError("downloaded file is empty")
    _validate_cached_file(part_path, expected_format, content_type=content_type)
    part_path.replace(destination)
    return DownloadResult(
        url=url,
        final_url=final_url,
        local_path=destination,
        byte_size=destination.stat().st_size,
        sha256=sha256_file(destination),
        content_type=content_type,
        content_length=content_length,
        etag=headers.get("ETag"),
        last_modified=headers.get("Last-Modified"),
        from_cache=False,
    )


def _validate_cached_file(
    path: Path,
    expected_format: str | None,
    *,
    content_type: str | None = None,
) -> None:
    if not path.exists():
        raise ValueError(f"cached file is missing: {path}")
    if path.stat().st_size == 0:
        raise ValueError(f"cached file is empty: {path}")

    with path.open("rb") as handle:
        prefix = handle.read(512)
    lowered = prefix.lower()
    if lowered.lstrip().startswith(b"<!doctype html") or lowered.lstrip().startswith(b"<html"):
        raise ValueError(f"cached file appears to be an HTML error page: {path}")
    if expected_format == "zip" and not prefix.startswith(b"PK"):
        raise ValueError(f"expected ZIP file but content is not a ZIP: {path}")
    if expected_format == "zip" and content_type and "html" in content_type.lower():
        raise ValueError(f"expected ZIP file but content type is HTML: {content_type}")
