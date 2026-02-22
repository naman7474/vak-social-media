from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    DECIMAL,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from vak_bot.db.base import Base


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    product_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    product_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    fabric: Mapped[str | None] = mapped_column(String(100), nullable=True)
    colors: Mapped[str | None] = mapped_column(Text, nullable=True)
    motif: Mapped[str | None] = mapped_column(String(200), nullable=True)
    artisan_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    days_to_make: Mapped[int | None] = mapped_column(Integer, nullable=True)
    technique: Mapped[str | None] = mapped_column(String(200), nullable=True)
    price: Mapped[float | None] = mapped_column(DECIMAL(10, 2), nullable=True)
    shopify_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active", server_default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    photos: Mapped[list[ProductPhoto]] = relationship(back_populates="product", cascade="all, delete-orphan")
    posts: Mapped[list[Post]] = relationship(back_populates="product")


class ProductPhoto(Base):
    __tablename__ = "product_photos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    photo_url: Mapped[str] = mapped_column(String(500), nullable=False)
    photo_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    product: Mapped[Product] = relationship(back_populates="photos")


class Post(Base):
    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(50), nullable=True)
    reference_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    reference_image: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_caption: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_hashtags: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_image_urls: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    style_brief: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    styled_image: Mapped[str | None] = mapped_column(String(500), nullable=True)
    caption: Mapped[str | None] = mapped_column(Text, nullable=True)
    hashtags: Mapped[str | None] = mapped_column(Text, nullable=True)
    alt_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    instagram_post_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    instagram_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    posted_by: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft", server_default="draft")
    media_type: Mapped[str] = mapped_column(String(20), nullable=False, default="single", server_default="single")
    input_photo_urls: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    telegram_photo_file_ids: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    selected_variant_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    publish_idempotency_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # ── Video / Reel fields ──
    detected_media_type: Mapped[str | None] = mapped_column(String(10), nullable=True)  # "image" | "reel"
    video_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    video_style_brief: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    video_type: Mapped[str | None] = mapped_column(String(20), nullable=True)  # fabric-flow, close-up, etc.
    start_frame_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    video_duration: Mapped[int | None] = mapped_column(Integer, nullable=True)
    thumb_offset_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    product: Mapped[Product | None] = relationship(back_populates="posts")
    variants: Mapped[list[PostVariant]] = relationship(back_populates="post", cascade="all, delete-orphan")
    sessions: Mapped[list[TelegramSession]] = relationship(back_populates="post", cascade="all, delete-orphan")
    job_runs: Mapped[list[JobRun]] = relationship(back_populates="post", cascade="all, delete-orphan")
    video_jobs: Mapped[list[VideoJob]] = relationship(back_populates="post", cascade="all, delete-orphan")


class PostVariant(Base):
    __tablename__ = "post_variants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id"), nullable=False)
    variant_index: Mapped[int] = mapped_column(Integer, nullable=False)
    preview_url: Mapped[str] = mapped_column(String(500), nullable=False)
    ssim_score: Mapped[float] = mapped_column(DECIMAL(5, 4), nullable=False)
    is_valid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    post: Mapped[Post] = relationship(back_populates="variants")
    items: Mapped[list[PostVariantItem]] = relationship(back_populates="variant", cascade="all, delete-orphan")


class PostVariantItem(Base):
    __tablename__ = "post_variant_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    variant_id: Mapped[int] = mapped_column(ForeignKey("post_variants.id"), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    image_url: Mapped[str] = mapped_column(String(500), nullable=False)

    variant: Mapped[PostVariant] = relationship(back_populates="items")


class TelegramSession(Base):
    __tablename__ = "telegram_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_user_id: Mapped[str] = mapped_column(String(50), nullable=False)
    chat_id: Mapped[str] = mapped_column(String(50), nullable=False)
    post_id: Mapped[int | None] = mapped_column(ForeignKey("posts.id"), nullable=True)
    state: Mapped[str] = mapped_column(String(50), nullable=False, default="idle", server_default="idle")
    context_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    post: Mapped[Post | None] = relationship(back_populates="sessions")


class JobRun(Base):
    __tablename__ = "job_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id"), nullable=False)
    stage: Mapped[str] = mapped_column(String(30), nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    post: Mapped[Post] = relationship(back_populates="job_runs")


Index("ix_posts_status_created_at", Post.status, Post.created_at)
Index("ix_telegram_sessions_user_state", TelegramSession.telegram_user_id, TelegramSession.state)


class VideoJob(Base):
    __tablename__ = "video_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id"), nullable=False)
    veo_operation_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", server_default="pending")
    variation_number: Mapped[int] = mapped_column(Integer, nullable=False)
    video_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    generation_time_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prompt_used: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    post: Mapped[Post] = relationship(back_populates="video_jobs")
