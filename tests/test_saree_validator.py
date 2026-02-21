import io

from PIL import Image

from vak_bot.pipeline.saree_validator import SareeValidator


def _make_img(color: tuple[int, int, int]) -> bytes:
    image = Image.new("RGB", (128, 128), color=color)
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    return buffer.getvalue()


def test_saree_validator_scores_high_for_same_image() -> None:
    validator = SareeValidator(threshold=0.6)
    original = _make_img((200, 150, 120))
    valid, score = validator.verify_preserved(original, original)
    assert valid
    assert score >= 0.99


def test_saree_validator_scores_lower_for_different_image() -> None:
    validator = SareeValidator(threshold=0.6)
    first = _make_img((10, 10, 10))
    second = _make_img((240, 240, 240))
    valid, score = validator.verify_preserved(first, second)
    assert not valid
    assert score < 0.6
