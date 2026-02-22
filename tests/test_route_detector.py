"""Tests for route_detector — URL pattern detection, user overrides, pipeline routing."""

from vak_bot.pipeline.route_detector import (
    confirm_media_type_from_mime,
    detect_media_type,
    detect_user_override,
    resolve_pipeline_type,
)


class TestDetectMediaType:
    def test_instagram_reel_url_detected(self) -> None:
        assert detect_media_type("https://www.instagram.com/reel/ABC123/") == "reel"

    def test_instagram_reels_url_detected(self) -> None:
        assert detect_media_type("https://instagram.com/reels/XYZ789/") == "reel"

    def test_instagram_image_url_detected(self) -> None:
        assert detect_media_type("https://www.instagram.com/p/ABC123/") == "image"

    def test_instagram_igtv_detected_as_reel(self) -> None:
        assert detect_media_type("https://www.instagram.com/tv/ABC123/") == "reel"

    def test_pinterest_returns_unknown(self) -> None:
        assert detect_media_type("https://www.pinterest.com/pin/12345/") == "unknown"

    def test_pin_it_returns_unknown(self) -> None:
        assert detect_media_type("https://pin.it/abc123") == "unknown"

    def test_unknown_domain(self) -> None:
        assert detect_media_type("https://youtube.com/watch?v=123") == "unknown"


class TestDetectUserOverride:
    def test_reel_override_make_it_a_reel(self) -> None:
        assert detect_user_override("make it a reel") == "reel"

    def test_reel_override_reel_this(self) -> None:
        assert detect_user_override("reel this") == "reel"

    def test_reel_override_video_keyword(self) -> None:
        assert detect_user_override("I want a video version") == "reel"

    def test_image_override_just_photo(self) -> None:
        assert detect_user_override("just the photo") == "image"

    def test_image_override_no_video(self) -> None:
        assert detect_user_override("no video please") == "image"

    def test_no_override_normal_text(self) -> None:
        assert detect_user_override("Check out this beautiful saree") is None

    def test_none_text(self) -> None:
        assert detect_user_override(None) is None

    def test_empty_text(self) -> None:
        assert detect_user_override("") is None


class TestResolvePipelineType:
    def test_reel_url_routes_to_reel(self) -> None:
        assert resolve_pipeline_type("https://www.instagram.com/reel/ABC123/") == "reel"

    def test_image_url_routes_to_image(self) -> None:
        assert resolve_pipeline_type("https://www.instagram.com/p/ABC123/") == "image"

    def test_user_override_beats_url(self) -> None:
        # URL says image, but user says reel — user wins
        assert resolve_pipeline_type(
            "https://www.instagram.com/p/ABC123/", "make it a reel"
        ) == "reel"

    def test_user_image_override_beats_reel_url(self) -> None:
        # URL says reel, but user says image — user wins
        assert resolve_pipeline_type(
            "https://www.instagram.com/reel/ABC/", "just the photo"
        ) == "image"

    def test_unknown_url_defaults_to_image(self) -> None:
        assert resolve_pipeline_type("https://pin.it/abc", None) == "image"
