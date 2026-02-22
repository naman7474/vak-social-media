from vak_bot.bot.parser import (
    extract_first_url,
    extract_product_code,
    is_supported_reference_url,
    parse_message_text,
)


def test_extract_url_and_product_code() -> None:
    text = "https://www.instagram.com/p/abc123 VAK-042"
    assert extract_first_url(text) == "https://www.instagram.com/p/abc123"
    assert extract_product_code(text) == "VAK-042"


def test_supported_reference_hosts() -> None:
    assert is_supported_reference_url("https://www.instagram.com/p/abc")
    assert is_supported_reference_url("https://pin.it/xyz")
    assert not is_supported_reference_url("https://youtube.com/watch?v=1")


def test_parse_action_command() -> None:
    parsed = parse_message_text("edit caption")
    assert parsed.command == "edit caption"
    assert parsed.source_url is None


def test_parse_reel_command_with_url() -> None:
    parsed = parse_message_text("/reel https://www.instagram.com/p/abc123 VAK-042")
    assert parsed.command == "/reel"
    assert parsed.source_url == "https://www.instagram.com/p/abc123"
    assert parsed.product_code == "VAK-042"
    assert parsed.media_override == "reel"


def test_parse_redo_with_video_type() -> None:
    parsed = parse_message_text("redo close-up")
    assert parsed.command == "redo close-up"
