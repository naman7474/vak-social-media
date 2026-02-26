from vak_bot.pipeline.orchestrator import _ad_structure_duration_seconds, _ffmpeg_available, _select_ad_structure


def test_ad_structure_duration_seconds_object_shape() -> None:
    structure = {
        "scenes": [
            {"duration_sec": 3},
            {"duration_sec": 7},
            {"duration_sec": 10},
        ]
    }
    assert _ad_structure_duration_seconds(structure) == 20


def test_select_ad_structure_picks_closest_preset(monkeypatch) -> None:
    config = {
        "video_presets": {
            "ad_structures": {
                "15_second_reel": {"scenes": [{"duration_sec": 5}, {"duration_sec": 10}]},
                "30_second_reel": {"scenes": [{"duration_sec": 10}, {"duration_sec": 10}, {"duration_sec": 10}]},
            }
        }
    }

    monkeypatch.setattr("vak_bot.pipeline.orchestrator.load_brand_config", lambda: config)

    assert _select_ad_structure("30_second_reel", 14) == "15_second_reel"
    assert _select_ad_structure("30_second_reel", 27) == "30_second_reel"


def test_select_ad_structure_fallbacks_to_default_without_duration(monkeypatch) -> None:
    monkeypatch.setattr("vak_bot.pipeline.orchestrator.load_brand_config", lambda: {"video_presets": {}})
    assert _select_ad_structure("30_second_reel", None) == "30_second_reel"


def test_ffmpeg_available_when_configured_path_exists(monkeypatch, tmp_path) -> None:
    fake_ffmpeg = tmp_path / "ffmpeg"
    fake_ffmpeg.write_text("")
    monkeypatch.setattr("vak_bot.pipeline.orchestrator.settings.ffmpeg_path", str(fake_ffmpeg))
    assert _ffmpeg_available() is True


def test_ffmpeg_unavailable_when_not_on_path(monkeypatch) -> None:
    monkeypatch.setattr("vak_bot.pipeline.orchestrator.settings.ffmpeg_path", "ffmpeg")
    monkeypatch.setattr("vak_bot.pipeline.orchestrator.shutil.which", lambda _cmd: None)
    assert _ffmpeg_available() is False
