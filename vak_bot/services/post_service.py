from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from vak_bot.db.models import Post, Product, ProductPhoto, TelegramSession
from vak_bot.enums import MediaType, PostStatus, SessionState


def get_or_create_session(db: Session, telegram_user_id: int, chat_id: int) -> TelegramSession:
    record = (
        db.query(TelegramSession)
        .filter(TelegramSession.telegram_user_id == str(telegram_user_id), TelegramSession.chat_id == str(chat_id))
        .first()
    )
    if record:
        return record

    record = TelegramSession(
        telegram_user_id=str(telegram_user_id),
        chat_id=str(chat_id),
        state=SessionState.IDLE.value,
        context_json={},
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def user_posts_today(db: Session, telegram_user_id: int) -> int:
    start = datetime.now(timezone.utc) - timedelta(days=1)
    return (
        db.query(func.count(Post.id))
        .filter(Post.created_by == str(telegram_user_id), Post.created_at >= start)
        .scalar()
        or 0
    )


def lookup_product_by_code(db: Session, product_code: str) -> Product | None:
    return db.query(Product).filter(Product.product_code == product_code.upper()).first()


def product_photo_urls(product: Product) -> list[str]:
    ordered = sorted(product.photos, key=lambda p: (not p.is_primary, p.id))
    return [photo.photo_url for photo in ordered]


def create_draft_post(
    db: Session,
    telegram_user_id: int,
    source_url: str,
    product: Product | None,
    input_photo_urls: list[str],
    telegram_photo_file_ids: list[str],
) -> Post:
    media_type = MediaType.CAROUSEL.value if len(input_photo_urls) > 1 else MediaType.SINGLE.value
    post = Post(
        created_by=str(telegram_user_id),
        product_id=product.id if product else None,
        reference_url=source_url,
        status=PostStatus.DRAFT.value,
        media_type=media_type,
        input_photo_urls=input_photo_urls,
        telegram_photo_file_ids=telegram_photo_file_ids,
    )
    db.add(post)
    db.commit()
    db.refresh(post)
    return post
