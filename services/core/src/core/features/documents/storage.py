"""Document blob storage - filesystem (local) and S3 backends behind one port.

Keys are always the tenant-scoped relative path
``{tenant_id}/{document_id}/v{version_number}``. Implementations reject any key
that escapes their namespace (mirrors ``identity.features.avatars.storage``).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import anyio

from core.core.config import settings


class DocumentStoragePort(ABC):
    """Blob storage contract for document payloads."""

    name: str = ""

    @abstractmethod
    async def put(self, key: str, data: bytes, content_type: str | None) -> None:
        """Store ``data`` at ``key``."""

    @abstractmethod
    async def get(self, key: str) -> bytes | None:
        """Return the bytes at ``key``, or None when absent."""

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Remove the object at ``key`` (no-op when absent)."""


class LocalDocumentStorage(DocumentStoragePort):
    """Filesystem-backed document storage rooted at ``base_dir``."""

    name = "local"

    def __init__(self, base_dir: str | Path) -> None:
        self.base_dir = Path(base_dir)

    def _resolve(self, key: str) -> Path:
        if not key or key.startswith("/") or ".." in key.replace("\\", "/").split("/"):
            raise ValueError(f"Invalid document storage key: {key!r}")
        path = self.base_dir / key
        try:
            path.resolve().relative_to(self.base_dir.resolve())
        except ValueError as exc:
            raise ValueError(f"Invalid document storage key: {key!r}") from exc
        return path

    async def put(self, key: str, data: bytes, content_type: str | None) -> None:
        path = self._resolve(key)
        await anyio.to_thread.run_sync(self._write, path, data)

    async def get(self, key: str) -> bytes | None:
        path = self._resolve(key)
        return await anyio.to_thread.run_sync(self._read, path)

    async def delete(self, key: str) -> None:
        path = self._resolve(key)
        await anyio.to_thread.run_sync(self._unlink, path)

    def _write(self, path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def _read(self, path: Path) -> bytes | None:
        if not path.is_file():
            return None
        return path.read_bytes()

    def _unlink(self, path: Path) -> None:
        if path.is_file():
            path.unlink()


class S3DocumentStorage(DocumentStoragePort):
    """S3-compatible document storage under ``prefix`` in ``bucket``.

    ``boto3`` is imported lazily inside the methods so the core service runs
    without it unless the S3 backend is selected (mirrors avatars). When
    ``endpoint_url`` is set (e.g. MinIO in dev) it is used verbatim; otherwise
    the default AWS region endpoint serves the bucket.
    """

    name = "s3"

    def __init__(
        self,
        *,
        bucket: str,
        prefix: str,
        region: str,
        endpoint_url: str | None = None,
    ) -> None:
        self.bucket = bucket
        self.prefix = prefix.strip("/")
        self.region = region
        self.endpoint_url = endpoint_url or None
        self._client: Any | None = None

    def _key(self, key: str) -> str:
        if not key or key.startswith("/") or ".." in key.replace("\\", "/").split("/"):
            raise ValueError(f"Invalid document storage key: {key!r}")
        return f"{self.prefix}/{key}"

    def _get_client(self) -> Any:
        if self._client is None:
            import boto3

            kwargs: dict[str, Any] = {"region_name": self.region or None}
            if self.endpoint_url:
                kwargs["endpoint_url"] = self.endpoint_url
            self._client = boto3.client("s3", **kwargs)
        return self._client

    async def put(self, key: str, data: bytes, content_type: str | None) -> None:
        client = self._get_client()
        put_kwargs: dict[str, Any] = {"Bucket": self.bucket, "Key": self._key(key), "Body": data}
        if content_type:
            put_kwargs["ContentType"] = content_type
        await anyio.to_thread.run_sync(lambda: client.put_object(**put_kwargs))

    async def get(self, key: str) -> bytes | None:
        client = self._get_client()
        try:
            response = await anyio.to_thread.run_sync(
                lambda: client.get_object(Bucket=self.bucket, Key=self._key(key))
            )
        except Exception:  # missing object -> None
            return None
        body = response["Body"]
        return await anyio.to_thread.run_sync(body.read)

    async def delete(self, key: str) -> None:
        client = self._get_client()
        await anyio.to_thread.run_sync(
            lambda: client.delete_object(Bucket=self.bucket, Key=self._key(key))
        )


def build_document_storage() -> DocumentStoragePort:
    """Construct the document storage backend selected by configuration."""
    backend = settings.DOCS_STORAGE_BACKEND.strip().lower()
    if backend == "s3":
        if not settings.DOCS_S3_BUCKET.strip():
            raise RuntimeError("DOCS_STORAGE_BACKEND=s3 requires DOCS_S3_BUCKET to be set")
        return S3DocumentStorage(
            bucket=settings.DOCS_S3_BUCKET,
            prefix=settings.DOCS_S3_PREFIX,
            region=settings.DOCS_S3_REGION,
            endpoint_url=settings.DOCS_S3_ENDPOINT_URL or None,
        )
    return LocalDocumentStorage(settings.DOCS_STORAGE_LOCAL_DIR)
