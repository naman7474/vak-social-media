from __future__ import annotations

import httpx
import structlog

from vak_bot.config import get_settings
from vak_bot.pipeline.errors import PublishError

logger = structlog.get_logger(__name__)


class MetaGraphPoster:
    def __init__(self) -> None:
        self.settings = get_settings()

    @property
    def _base(self) -> str:
        return f"https://graph.facebook.com/{self.settings.meta_graph_api_version}"

    def _params(self) -> dict:
        return {"access_token": self.settings.meta_page_access_token}

    def post_single_image(self, image_url: str, caption: str, alt_text: str, idempotency_key: str) -> dict:
        if self.settings.dry_run:
            return {
                "id": f"dryrun_{idempotency_key}",
                "permalink": f"https://instagram.com/p/{idempotency_key}",
            }

        try:
            with httpx.Client(timeout=60.0) as client:
                create_resp = client.post(
                    f"{self._base}/{self.settings.instagram_business_account_id}/media",
                    params=self._params(),
                    data={
                        "image_url": image_url,
                        "caption": caption,
                        "alt_text": alt_text,
                    },
                )
                create_resp.raise_for_status()
                container_id = create_resp.json()["id"]

                publish_resp = client.post(
                    f"{self._base}/{self.settings.instagram_business_account_id}/media_publish",
                    params=self._params(),
                    data={"creation_id": container_id},
                )
                publish_resp.raise_for_status()
                media_id = publish_resp.json()["id"]

                permalink_resp = client.get(
                    f"{self._base}/{media_id}",
                    params={**self._params(), "fields": "permalink"},
                )
                permalink_resp.raise_for_status()
                permalink = permalink_resp.json().get("permalink", "")

            return {"id": media_id, "permalink": permalink}
        except httpx.HTTPStatusError as exc:
            body = exc.response.text[:600] if exc.response is not None else ""
            logger.error(
                "meta_publish_http_error",
                method="single_image",
                status_code=exc.response.status_code if exc.response is not None else None,
                body=body,
            )
            raise PublishError(f"{exc} | {body}") from exc
        except Exception as exc:
            raise PublishError(str(exc)) from exc

    def post_carousel(self, image_urls: list[str], caption: str, alt_text: str, idempotency_key: str) -> dict:
        if self.settings.dry_run:
            return {
                "id": f"dryrun_{idempotency_key}",
                "permalink": f"https://instagram.com/p/{idempotency_key}",
            }

        try:
            children_ids: list[str] = []
            with httpx.Client(timeout=60.0) as client:
                for idx, image_url in enumerate(image_urls, start=1):
                    logger.info("meta_carousel_child_create", position=idx, total=len(image_urls))
                    media_resp = client.post(
                        f"{self._base}/{self.settings.instagram_business_account_id}/media",
                        params=self._params(),
                        data={"image_url": image_url, "is_carousel_item": "true"},
                    )
                    media_resp.raise_for_status()
                    children_ids.append(media_resp.json()["id"])

                logger.info("meta_carousel_container_create", children_count=len(children_ids))
                carousel_resp = client.post(
                    f"{self._base}/{self.settings.instagram_business_account_id}/media",
                    params=self._params(),
                    data={
                        "media_type": "CAROUSEL",
                        "children": ",".join(children_ids),
                        "caption": caption,
                    },
                )
                carousel_resp.raise_for_status()
                container_id = carousel_resp.json()["id"]

                publish_resp = client.post(
                    f"{self._base}/{self.settings.instagram_business_account_id}/media_publish",
                    params=self._params(),
                    data={"creation_id": container_id},
                )
                publish_resp.raise_for_status()
                media_id = publish_resp.json()["id"]

                permalink_resp = client.get(
                    f"{self._base}/{media_id}",
                    params={**self._params(), "fields": "permalink"},
                )
                permalink_resp.raise_for_status()
                permalink = permalink_resp.json().get("permalink", "")

            return {"id": media_id, "permalink": permalink}
        except httpx.HTTPStatusError as exc:
            body = exc.response.text[:600] if exc.response is not None else ""
            logger.error(
                "meta_publish_http_error",
                method="carousel",
                status_code=exc.response.status_code if exc.response is not None else None,
                body=body,
                children_created=len(children_ids),
            )
            raise PublishError(f"{exc} | {body}") from exc
        except Exception as exc:
            raise PublishError(str(exc)) from exc

    def post_reel(
        self,
        video_s3_url: str,
        caption: str,
        thumb_offset_ms: int = 0,
        share_to_feed: bool = True,
    ) -> dict:
        """Post a video as an Instagram Reel via Meta Graph API."""
        if self.settings.dry_run:
            return {
                "id": f"dryrun_reel_{thumb_offset_ms}",
                "permalink": "https://instagram.com/reel/dryrun",
            }

        ig_user_id = self.settings.instagram_business_account_id

        try:
            with httpx.Client(timeout=120.0) as client:
                # Step 1: Create Reel media container
                container_resp = client.post(
                    f"{self._base}/{ig_user_id}/media",
                    params=self._params(),
                    data={
                        "media_type": "REELS",
                        "video_url": video_s3_url,
                        "caption": caption,
                        "share_to_feed": str(share_to_feed).lower(),
                        "thumb_offset": str(thumb_offset_ms),
                    },
                )
                container_resp.raise_for_status()
                container_id = container_resp.json()["id"]

                # Step 2: Poll container status until video is processed
                import time
                max_retries = 30
                for _ in range(max_retries):
                    status_resp = client.get(
                        f"{self._base}/{container_id}",
                        params={**self._params(), "fields": "status_code"},
                    )
                    status_resp.raise_for_status()
                    status = status_resp.json().get("status_code")

                    if status == "FINISHED":
                        break
                    elif status == "ERROR":
                        raise PublishError("Instagram video processing failed")
                    time.sleep(10)

                # Step 3: Publish the Reel
                publish_resp = client.post(
                    f"{self._base}/{ig_user_id}/media_publish",
                    params=self._params(),
                    data={"creation_id": container_id},
                )
                publish_resp.raise_for_status()
                media_id = publish_resp.json()["id"]

                # Step 4: Get permalink
                permalink_resp = client.get(
                    f"{self._base}/{media_id}",
                    params={**self._params(), "fields": "permalink"},
                )
                permalink_resp.raise_for_status()
                permalink = permalink_resp.json().get("permalink", "")

            return {"id": media_id, "permalink": permalink}
        except httpx.HTTPStatusError as exc:
            body = exc.response.text[:600] if exc.response is not None else ""
            logger.error(
                "meta_publish_http_error",
                method="reel",
                status_code=exc.response.status_code if exc.response is not None else None,
                body=body,
            )
            raise PublishError(f"{exc} | {body}") from exc
        except Exception as exc:
            raise PublishError(str(exc)) from exc

    def refresh_page_token(self) -> dict:
        if self.settings.dry_run:
            return {"access_token": "dry-run-token", "expires_in": 60 * 24 * 3600}

        if not self.settings.meta_page_access_token:
            raise PublishError("Missing META_PAGE_ACCESS_TOKEN")

        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.get(
                    f"{self._base}/oauth/access_token",
                    params={
                        "grant_type": "fb_exchange_token",
                        "client_id": self.settings.meta_app_id,
                        "client_secret": self.settings.meta_app_secret,
                        "fb_exchange_token": self.settings.meta_page_access_token,
                    },
                )
                response.raise_for_status()
                return response.json()
        except Exception as exc:
            raise PublishError(str(exc)) from exc
