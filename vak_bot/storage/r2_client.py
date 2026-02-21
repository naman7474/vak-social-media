from __future__ import annotations

import uuid
from urllib.parse import urlparse

import boto3

from vak_bot.config import get_settings


class R2StorageClient:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._dry_run = self.settings.dry_run
        self._bucket = self.settings.storage_bucket
        self._public_base_url = self.settings.storage_public_base_url.rstrip("/")
        self._endpoint = self.settings.storage_endpoint_url.rstrip("/")

        self._client = None
        if not self._dry_run:
            self._client = boto3.client(
                "s3",
                aws_access_key_id=self.settings.storage_access_key_id,
                aws_secret_access_key=self.settings.storage_secret_access_key,
                endpoint_url=self.settings.storage_endpoint_url,
                region_name=self.settings.storage_region,
            )

    def upload_bytes(self, key: str, data: bytes, content_type: str = "image/jpeg") -> str:
        safe_key = key.strip("/") or f"generated/{uuid.uuid4().hex}.jpg"
        if self._dry_run:
            base = self._public_base_url or "https://example.com"
            return f"{base}/{safe_key}"

        assert self._client is not None
        self._client.put_object(
            Bucket=self._bucket,
            Key=safe_key,
            Body=data,
            ContentType=content_type,
        )
        if self._public_base_url:
            return f"{self._public_base_url}/{safe_key}"
        return f"{self._endpoint}/{self._bucket}/{safe_key}"

    def delete_by_url(self, url: str) -> None:
        if self._dry_run or not url:
            return

        assert self._client is not None
        parsed = urlparse(url)
        key = parsed.path.strip("/")
        if self._bucket and key.startswith(f"{self._bucket}/"):
            key = key[len(self._bucket) + 1 :]
        self._client.delete_object(Bucket=self._bucket, Key=key)
