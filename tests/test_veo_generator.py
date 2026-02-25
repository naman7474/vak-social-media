"""Tests for VeoGenerator — prompt building, video type presets, dry-run mode."""

from vak_bot.pipeline.errors import VeoGenerationError
from vak_bot.pipeline.veo_generator import VIDEO_TYPE_PROMPTS, VeoGenerator
from vak_bot.schemas import StyleBrief, VideoAnalysis


def _make_style_brief(video_type: str = "fabric-flow", layout: str = "flat-lay") -> StyleBrief:
    return StyleBrief.model_validate({
        "layout_type": layout,
        "color_mood": {
            "temperature": "warm",
            "dominant_colors": ["#D4A574", "#8B6914"],
            "palette_name": "earthy",
        },
        "vibe_words": ["warm", "artisan"],
        "video_analysis": {
            "camera_motion": "slow-pan",
            "motion_type": "fabric-flow",
            "motion_elements": "silk fabric flowing in breeze",
            "pacing": "slow-dreamy",
            "audio_mood": "ambient-nature",
            "recommended_video_type": video_type,
        },
    })


class TestBuildVideoPrompt:
    def test_fabric_flow_prompt_contains_keywords(self) -> None:
        gen = VeoGenerator()
        brief = _make_style_brief("fabric-flow")
        prompt = gen.build_video_prompt(brief)
        assert "fabric" in prompt.lower()
        assert "saree" in prompt.lower()
        assert "9:16" in prompt

    def test_close_up_prompt_contains_zoom(self) -> None:
        gen = VeoGenerator()
        brief = _make_style_brief("close-up")
        prompt = gen.build_video_prompt(brief, video_type="close-up")
        assert "zoom" in prompt.lower()

    def test_auto_detect_from_layout(self) -> None:
        """When no video_analysis, video type should be inferred from layout_type."""
        gen = VeoGenerator()
        brief = StyleBrief.model_validate({
            "layout_type": "close-up",
            "color_mood": {"temperature": "warm", "dominant_colors": ["#D4A574"], "palette_name": "earthy"},
            "vibe_words": ["warm", "details"],
        })
        prompt = gen.build_video_prompt(brief)
        assert "zoom" in prompt.lower()

    def test_prompt_includes_style_context(self) -> None:
        gen = VeoGenerator()
        brief = _make_style_brief()
        prompt = gen.build_video_prompt(brief)
        assert "earthy" in prompt.lower()
        assert "warm" in prompt.lower()
        assert "CRITICAL RULES" in prompt

    def test_prompt_includes_critical_saree_rule(self) -> None:
        gen = VeoGenerator()
        brief = _make_style_brief()
        prompt = gen.build_video_prompt(brief)
        assert "saree" in prompt.lower()
        assert "remain EXACTLY" in prompt


class TestVideoTypePresets:
    def test_all_four_types_have_prompts(self) -> None:
        expected = {"fabric-flow", "close-up", "lifestyle", "reveal"}
        assert set(VIDEO_TYPE_PROMPTS.keys()) == expected

    def test_each_preset_is_nonempty(self) -> None:
        for key, prompt in VIDEO_TYPE_PROMPTS.items():
            assert len(prompt) > 20, f"Preset '{key}' is too short"


class TestVideoAnalysisSchema:
    def test_style_brief_with_video_analysis(self) -> None:
        brief = _make_style_brief()
        assert brief.video_analysis is not None
        assert brief.video_analysis.camera_motion == "slow-pan"
        assert brief.video_analysis.recommended_video_type == "fabric-flow"

    def test_style_brief_without_video_analysis(self) -> None:
        brief = StyleBrief.model_validate({
            "layout_type": "flat-lay",
            "color_mood": {"temperature": "warm", "dominant_colors": ["#D4A574"], "palette_name": "earthy"},
            "vibe_words": ["warm", "artisan"],
        })
        assert brief.video_analysis is None


class TestVariationResilience:
    def test_generate_reel_variations_continues_when_one_fails(self, monkeypatch) -> None:
        gen = VeoGenerator()
        brief = _make_style_brief()

        calls = {"n": 0}

        def _fake_generate(*args, **kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                return "/tmp/ok.mp4"
            raise VeoGenerationError("simulated veo failure")

        monkeypatch.setattr(gen, "generate_reel_from_styled_image", _fake_generate)
        results = gen.generate_reel_variations("/tmp/start.jpg", brief)
        assert results == ["/tmp/ok.mp4"]

    def test_generate_reel_variations_raises_when_all_fail(self, monkeypatch) -> None:
        gen = VeoGenerator()
        brief = _make_style_brief()

        def _always_fail(*args, **kwargs):
            raise VeoGenerationError("simulated veo failure")

        monkeypatch.setattr(gen, "generate_reel_from_styled_image", _always_fail)

        try:
            gen.generate_reel_variations("/tmp/start.jpg", brief)
            assert False, "Expected VeoGenerationError"
        except VeoGenerationError as exc:
            assert "No video variation was successfully generated" in str(exc)
            assert "simulated veo failure" in str(exc)


class TestOperationExtraction:
    def test_extract_generated_video_surfaces_rai_filter_details(self) -> None:
        gen = VeoGenerator()

        class _Response:
            generated_videos = []
            rai_media_filtered_count = 1
            rai_media_filtered_reasons = ["SAFETY"]

        class _Operation:
            error = None
            response = _Response()
            result = None

        try:
            gen._extract_generated_video(_Operation())
            assert False, "Expected VeoGenerationError"
        except VeoGenerationError as exc:
            assert "rai_filtered_count=1" in str(exc)
            assert "SAFETY" in str(exc)


class TestAdStructureParsing:
    def test_generate_multi_scene_ad_supports_object_preset_shape(self, monkeypatch, tmp_path) -> None:
        gen = VeoGenerator()
        brief = _make_style_brief()

        calls = {"n": 0}

        def _fake_generate(*args, **kwargs):
            calls["n"] += 1
            return str(tmp_path / f"scene_{calls['n']}.mp4")

        monkeypatch.setattr(gen, "generate_reel_from_styled_image", _fake_generate)
        result = gen.generate_multi_scene_ad(
            styled_frame_path="/tmp/start.jpg",
            style_brief=brief,
            ad_structure="30_second_reel",
        )

        assert len(result) >= 1
        assert result[0]["type"] in {"fabric-flow", "close-up", "lifestyle", "reveal"}
        assert all("duration" in scene for scene in result)
