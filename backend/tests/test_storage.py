"""The fake store, and one round trip through the real one when it answers."""

import socket
import uuid
from urllib.parse import urlparse

import httpx
import pytest

from app.core.config import Settings
from app.storage.client import ObjectNotFoundError, S3Storage
from tests.fakes import FakeStorage


async def test_fake_storage_round_trip() -> None:
    storage = FakeStorage()

    assert await storage.head("missing") is None
    with pytest.raises(ObjectNotFoundError):
        await storage.get_bytes("missing")
    await storage.put_bytes("incoming/x", b"abc", "text/plain")
    assert await storage.head("incoming/x") == 3
    assert await storage.get_bytes("incoming/x") == b"abc"


def _answers(url: str) -> bool:
    parts = urlparse(url)
    try:
        with socket.create_connection((parts.hostname or "", parts.port or 80), 1):
            return True
    except OSError:
        return False


async def test_round_trip_through_the_object_store(settings: Settings) -> None:
    if not _answers(settings.STORAGE_ENDPOINT_URL):
        pytest.skip(f"{settings.STORAGE_ENDPOINT_URL} does not answer")
    storage = S3Storage.from_settings(settings)
    await storage.ensure_bucket()
    key = f"test/{uuid.uuid4()}.txt"
    data = b"hot dog?"
    assert await storage.head(key) is None

    put_url = await storage.presign_put(key, "text/plain", expires_s=60)
    async with httpx.AsyncClient() as client:
        uploaded = await client.put(
            put_url, content=data, headers={"Content-Type": "text/plain"}
        )
        assert uploaded.status_code == 200, uploaded.text

        assert await storage.head(key) == len(data)
        assert await storage.get_bytes(key) == data

        get_url = await storage.presign_get(key, expires_s=60)
        downloaded = await client.get(get_url)
        assert downloaded.status_code == 200, downloaded.text
        assert downloaded.content == data
