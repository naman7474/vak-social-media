"""initial schema

Revision ID: 20260221_0001
Revises:
Create Date: 2026-02-21 12:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20260221_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "products",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("product_code", sa.String(length=20), nullable=False),
        sa.Column("product_name", sa.String(length=200), nullable=True),
        sa.Column("product_type", sa.String(length=50), nullable=True),
        sa.Column("fabric", sa.String(length=100), nullable=True),
        sa.Column("colors", sa.Text(), nullable=True),
        sa.Column("motif", sa.String(length=200), nullable=True),
        sa.Column("artisan_name", sa.String(length=100), nullable=True),
        sa.Column("days_to_make", sa.Integer(), nullable=True),
        sa.Column("technique", sa.String(length=200), nullable=True),
        sa.Column("price", sa.DECIMAL(precision=10, scale=2), nullable=True),
        sa.Column("shopify_url", sa.String(length=500), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("product_code", name="uq_products_product_code"),
    )
    op.create_index("ix_products_product_code", "products", ["product_code"])

    op.create_table(
        "posts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=True),
        sa.Column("created_by", sa.String(length=50), nullable=True),
        sa.Column("reference_url", sa.String(length=500), nullable=True),
        sa.Column("reference_image", sa.String(length=500), nullable=True),
        sa.Column("source_caption", sa.Text(), nullable=True),
        sa.Column("source_hashtags", sa.Text(), nullable=True),
        sa.Column("source_image_urls", sa.JSON(), nullable=True),
        sa.Column("style_brief", sa.JSON(), nullable=True),
        sa.Column("styled_image", sa.String(length=500), nullable=True),
        sa.Column("caption", sa.Text(), nullable=True),
        sa.Column("hashtags", sa.Text(), nullable=True),
        sa.Column("alt_text", sa.Text(), nullable=True),
        sa.Column("instagram_post_id", sa.String(length=100), nullable=True),
        sa.Column("instagram_url", sa.String(length=500), nullable=True),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("posted_by", sa.String(length=50), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="draft"),
        sa.Column("media_type", sa.String(length=20), nullable=False, server_default="single"),
        sa.Column("input_photo_urls", sa.JSON(), nullable=True),
        sa.Column("telegram_photo_file_ids", sa.JSON(), nullable=True),
        sa.Column("selected_variant_index", sa.Integer(), nullable=True),
        sa.Column("publish_idempotency_key", sa.String(length=120), nullable=True),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("detected_media_type", sa.String(length=10), nullable=True),
        sa.Column("video_url", sa.String(length=500), nullable=True),
        sa.Column("video_style_brief", sa.JSON(), nullable=True),
        sa.Column("video_type", sa.String(length=20), nullable=True),
        sa.Column("start_frame_url", sa.String(length=500), nullable=True),
        sa.Column("video_duration", sa.Integer(), nullable=True),
        sa.Column("thumb_offset_ms", sa.Integer(), nullable=True),
    )
    op.create_index("ix_posts_status_created_at", "posts", ["status", "created_at"])

    op.create_table(
        "product_photos",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("photo_url", sa.String(length=500), nullable=False),
        sa.Column("photo_type", sa.String(length=30), nullable=True),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )

    op.create_table(
        "post_variants",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("post_id", sa.Integer(), sa.ForeignKey("posts.id"), nullable=False),
        sa.Column("variant_index", sa.Integer(), nullable=False),
        sa.Column("preview_url", sa.String(length=500), nullable=False),
        sa.Column("ssim_score", sa.DECIMAL(precision=5, scale=4), nullable=False),
        sa.Column("is_valid", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )

    op.create_table(
        "post_variant_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("variant_id", sa.Integer(), sa.ForeignKey("post_variants.id"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("image_url", sa.String(length=500), nullable=False),
    )

    op.create_table(
        "telegram_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("telegram_user_id", sa.String(length=50), nullable=False),
        sa.Column("chat_id", sa.String(length=50), nullable=False),
        sa.Column("post_id", sa.Integer(), sa.ForeignKey("posts.id"), nullable=True),
        sa.Column("state", sa.String(length=50), nullable=False, server_default="idle"),
        sa.Column("context_json", sa.JSON(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index(
        "ix_telegram_sessions_user_state",
        "telegram_sessions",
        ["telegram_user_id", "state"],
    )

    op.create_table(
        "job_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("post_id", sa.Integer(), sa.ForeignKey("posts.id"), nullable=False),
        sa.Column("stage", sa.String(length=30), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "video_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("post_id", sa.Integer(), sa.ForeignKey("posts.id"), nullable=False),
        sa.Column("veo_operation_id", sa.String(length=200), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("variation_number", sa.Integer(), nullable=False),
        sa.Column("video_url", sa.String(length=500), nullable=True),
        sa.Column("generation_time_seconds", sa.Integer(), nullable=True),
        sa.Column("prompt_used", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("video_jobs")
    op.drop_table("job_runs")
    op.drop_index("ix_telegram_sessions_user_state", table_name="telegram_sessions")
    op.drop_table("telegram_sessions")
    op.drop_table("post_variant_items")
    op.drop_table("post_variants")
    op.drop_table("product_photos")
    op.drop_index("ix_posts_status_created_at", table_name="posts")
    op.drop_table("posts")
    op.drop_index("ix_products_product_code", table_name="products")
    op.drop_table("products")
