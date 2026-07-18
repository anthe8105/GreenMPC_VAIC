from __future__ import annotations

from io import BytesIO
from pathlib import Path
from urllib.error import URLError

import pytest

from greenmpc.data import download
from greenmpc.data.download import download_file, sha256_file


class FakeHeaders(dict):
    def get(self, key, default=None):
        return super().get(key, default)


class FakeResponse:
    def __init__(self, body: bytes, headers: dict | None = None, url: str = "https://example.test/file"):
        self._body = BytesIO(body)
        self.headers = FakeHeaders(headers or {})
        self._url = url

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def read(self, size: int = -1) -> bytes:
        return self._body.read(size)

    def geturl(self) -> str:
        return self._url


def test_atomic_download_succeeds(monkeypatch, tmp_path: Path) -> None:
    body = b"YEAR,MO,DY,HR,T2M\n2013,1,1,0,25\n"

    monkeypatch.setattr(download, "urlopen", lambda request, timeout: FakeResponse(body, {"Content-Type": "text/csv"}))
    target = tmp_path / "nasa.csv"

    result = download_file(
        "https://example.test/nasa.csv",
        target,
        user_agent="test",
        timeout_seconds=1,
        retries=0,
        retry_backoff_seconds=0,
        expected_format="csv",
    )

    assert target.read_bytes() == body
    assert not (tmp_path / "nasa.csv.part").exists()
    assert result.sha256 == sha256_file(target)


def test_failed_download_does_not_leave_completed_target(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(download, "urlopen", lambda request, timeout: (_ for _ in ()).throw(URLError("down")))
    target = tmp_path / "missing.csv"

    with pytest.raises(RuntimeError):
        download_file(
            "https://example.test/missing.csv",
            target,
            user_agent="test",
            timeout_seconds=1,
            retries=0,
            retry_backoff_seconds=0,
        )

    assert not target.exists()
    assert not (tmp_path / "missing.csv.part").exists()


def test_retry_behavior_works(monkeypatch, tmp_path: Path) -> None:
    calls = {"count": 0}

    def fake_urlopen(request, timeout):
        calls["count"] += 1
        if calls["count"] == 1:
            raise URLError("temporary")
        return FakeResponse(b"ok")

    monkeypatch.setattr(download, "urlopen", fake_urlopen)
    target = tmp_path / "file.txt"

    download_file(
        "https://example.test/file.txt",
        target,
        user_agent="test",
        timeout_seconds=1,
        retries=1,
        retry_backoff_seconds=0,
    )

    assert calls["count"] == 2
    assert target.read_bytes() == b"ok"


def test_valid_cache_prevents_redownload(monkeypatch, tmp_path: Path) -> None:
    target = tmp_path / "cached.csv"
    target.write_text("YEAR,MO,DY,HR,T2M\n2013,1,1,0,25\n", encoding="utf-8")
    calls = {"count": 0}

    def fake_urlopen(request, timeout):
        calls["count"] += 1
        return FakeResponse(b"new")

    monkeypatch.setattr(download, "urlopen", fake_urlopen)
    result = download_file(
        "https://example.test/cached.csv",
        target,
        user_agent="test",
        timeout_seconds=1,
        retries=0,
        retry_backoff_seconds=0,
        expected_format="csv",
    )

    assert result.from_cache
    assert calls["count"] == 0


def test_force_reacquires(monkeypatch, tmp_path: Path) -> None:
    target = tmp_path / "cached.csv"
    target.write_text("old", encoding="utf-8")
    monkeypatch.setattr(download, "urlopen", lambda request, timeout: FakeResponse(b"new"))

    result = download_file(
        "https://example.test/cached.csv",
        target,
        user_agent="test",
        timeout_seconds=1,
        retries=0,
        retry_backoff_seconds=0,
        force=True,
    )

    assert not result.from_cache
    assert target.read_bytes() == b"new"


def test_sha256_is_calculated_correctly(tmp_path: Path) -> None:
    target = tmp_path / "hash.txt"
    target.write_text("abc", encoding="utf-8")

    assert sha256_file(target) == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def test_html_error_page_rejected_for_zip(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(download, "urlopen", lambda request, timeout: FakeResponse(b"<html>error</html>", {"Content-Type": "text/html"}))

    with pytest.raises(RuntimeError, match="HTML"):
        download_file(
            "https://example.test/file.zip",
            tmp_path / "file.zip",
            user_agent="test",
            timeout_seconds=1,
            retries=0,
            retry_backoff_seconds=0,
            expected_format="zip",
        )
