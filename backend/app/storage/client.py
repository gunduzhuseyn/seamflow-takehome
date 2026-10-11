"""Object storage behind the S3 API: RustFS in Compose, Cloudflare R2 live.

Every method of `S3Storage` runs its boto3 call in a thread. The presigned
URLs come from a client on the public endpoint, so the browser can reach
them. `tests/fakes.py` has the in-memory `FakeStorage`.
"""

import asyncio
import logging
from collections.abc import Sequence
from typing import TYPE_CHECKING, Annotated, Protocol, Self

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from fastapi import Depends, Request

from app.core.config import Settings

if TYPE_CHECKING:
    # boto3-stubs is a dev dependency. The image installs without it.
    from mypy_boto3_s3 import S3Client

log = logging.getLogger("app.storage")

# Error codes of a missing key or bucket, by store and by call.
MISSING_CODES = frozenset({"404", "NoSuchKey", "NotFound", "NoSuchBucket"})
CORS_MAX_AGE_SECONDS = 3600


class ObjectNotFoundError(Exception):
    """`get_bytes` found no object under the key."""


class Storage(Protocol):
    async def presign_put(self, key: str, content_type: str, expires_s: int) -> str:
        """A URL the browser PUTs the file to, with that Content-Type."""
        ...

    async def presign_get(self, key: str, expires_s: int) -> str: ...

    async def head(self, key: str) -> int | None:
        """The size in bytes, or None when the key is missing."""
        ...

    async def get_bytes(self, key: str) -> bytes: ...

    async def put_bytes(self, key: str, data: bytes, content_type: str) -> None: ...

    async def ensure_bucket(self) -> None:
        """Create the bucket if missing and set its CORS rule. Development only."""
        ...


def _error_code(error: ClientError) -> str:
    details = error.response.get("Error")
    return str(details.get("Code", "")) if details else ""


class S3Storage:
    def __init__(
        self,
        *,
        endpoint_url: str,
        public_endpoint_url: str,
        access_key_id: str,
        secret_access_key: str,
        bucket: str,
        region: str,
        cors_origins: Sequence[str],
    ) -> None:
        # Path style: `host/bucket/key`. RustFS has no per-bucket hostnames.
        config = Config(signature_version="s3v4", s3={"addressing_style": "path"})

        def client(url: str) -> S3Client:
            return boto3.client(  # pyright: ignore[reportUnknownMemberType]
                "s3",
                endpoint_url=url,
                aws_access_key_id=access_key_id,
                aws_secret_access_key=secret_access_key,
                region_name=region,
                config=config,
            )

        self._client = client(endpoint_url)
        # The signature covers the host, so presigned URLs need a client on
        # the host the browser uses.
        self._public = (
            self._client
            if public_endpoint_url == endpoint_url
            else client(public_endpoint_url)
        )
        self.bucket = bucket
        self._cors_origins = list(cors_origins)

    @classmethod
    def from_settings(cls, settings: Settings) -> Self:
        return cls(
            endpoint_url=settings.STORAGE_ENDPOINT_URL,
            public_endpoint_url=settings.STORAGE_PUBLIC_ENDPOINT_URL,
            access_key_id=settings.STORAGE_ACCESS_KEY_ID,
            secret_access_key=settings.STORAGE_SECRET_ACCESS_KEY,
            bucket=settings.STORAGE_BUCKET,
            region=settings.STORAGE_REGION,
            cors_origins=settings.CORS_ORIGINS,
        )

    async def presign_put(self, key: str, content_type: str, expires_s: int) -> str:
        return await asyncio.to_thread(
            self._public.generate_presigned_url,
            "put_object",
            Params={"Bucket": self.bucket, "Key": key, "ContentType": content_type},
            ExpiresIn=expires_s,
        )

    async def presign_get(self, key: str, expires_s: int) -> str:
        return await asyncio.to_thread(
            self._public.generate_presigned_url,
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=expires_s,
        )

    async def head(self, key: str) -> int | None:
        def head() -> int | None:
            try:
                response = self._client.head_object(Bucket=self.bucket, Key=key)
            except ClientError as error:
                if _error_code(error) in MISSING_CODES:
                    return None
                raise
            return response["ContentLength"]

        return await asyncio.to_thread(head)

    async def get_bytes(self, key: str) -> bytes:
        def get() -> bytes:
            try:
                response = self._client.get_object(Bucket=self.bucket, Key=key)
            except ClientError as error:
                if _error_code(error) in MISSING_CODES:
                    raise ObjectNotFoundError(key) from error
                raise
            return response["Body"].read()

        return await asyncio.to_thread(get)

    async def put_bytes(self, key: str, data: bytes, content_type: str) -> None:
        await asyncio.to_thread(
            self._client.put_object,
            Bucket=self.bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
        )

    async def ensure_bucket(self) -> None:
        def ensure() -> None:
            try:
                self._client.head_bucket(Bucket=self.bucket)
            except ClientError as error:
                if _error_code(error) not in MISSING_CODES:
                    raise
                self._client.create_bucket(Bucket=self.bucket)
                log.info("bucket created", extra={"bucket": self.bucket})
            self._client.put_bucket_cors(
                Bucket=self.bucket,
                CORSConfiguration={
                    "CORSRules": [
                        {
                            "AllowedOrigins": self._cors_origins,
                            "AllowedMethods": ["PUT", "GET"],
                            "AllowedHeaders": ["*"],
                            "MaxAgeSeconds": CORS_MAX_AGE_SECONDS,
                        }
                    ]
                },
            )

        await asyncio.to_thread(ensure)


def get_storage(request: Request) -> Storage:
    """The storage the lifespan built from the STORAGE_* settings."""
    return request.app.state.storage


StorageDep = Annotated[Storage, Depends(get_storage)]
