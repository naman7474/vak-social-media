from __future__ import annotations

import httpx

from vak_bot.config import get_settings
from vak_bot.pipeline.errors import PublishError


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
                for image_url in image_urls:
                    media_resp = client.post(
                        f"{self._base}/{self.settings.instagram_business_account_id}/media",
                        params=self._params(),
                        data={"image_url": image_url, "is_carousel_item": "true"},
                    )
                    media_resp.raise_for_status()
                    children_ids.append(media_resp.json()["id"])

                carousel_resp = client.post(
                    f"{self._base}/{self.settings.instagram_business_account_id}/media",
                    params=self._params(),
                    data={
                        "media_type": "CAROUSEL",
                        "children": ",".join(children_ids),
                        "caption": caption,
                        "alt_text": alt_text,
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
