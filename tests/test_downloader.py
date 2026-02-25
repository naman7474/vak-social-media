from vak_bot.pipeline.downloader import _extract_video_duration_seconds, _parse_duration_seconds


def test_parse_duration_seconds_from_clock_string() -> None:
    assert _parse_duration_seconds("00:30") == 30
    assert _parse_duration_seconds("01:02:03") == 3723


def test_parse_duration_seconds_from_numeric_and_suffix() -> None:
    assert _parse_duration_seconds(29.6) == 30
    assert _parse_duration_seconds("29s") == 29
    assert _parse_duration_seconds("32000ms") == 32


def test_extract_video_duration_seconds_prefers_known_keys() -> None:
    payload = {"video_duration_seconds": "18", "duration": "00:25"}
    assert _extract_video_duration_seconds(payload) == 18


def test_extract_video_duration_seconds_from_nested_metadata() -> None:
    payload = {"video_metadata": {"duration_sec": "14"}}
    assert _extract_video_duration_seconds(payload) == 14
