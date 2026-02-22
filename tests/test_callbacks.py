from vak_bot.bot.callbacks import make_callback, parse_callback
from vak_bot.enums import CallbackAction


def test_parse_video_select_callback() -> None:
    data = make_callback(12, 2, CallbackAction.SELECT_VIDEO)
    parsed = parse_callback(data)
    assert parsed is not None
    assert parsed.post_id == 12
    assert parsed.variant == 2
    assert parsed.action == CallbackAction.SELECT_VIDEO


def test_parse_extend_callback() -> None:
    data = make_callback(7, 0, CallbackAction.EXTEND)
    parsed = parse_callback(data)
    assert parsed is not None
    assert parsed.action == CallbackAction.EXTEND
