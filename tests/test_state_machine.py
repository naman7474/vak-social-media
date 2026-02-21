from vak_bot.enums import PostStatus, SessionState
from vak_bot.services.state_machine import can_transition_post, can_transition_session


def test_post_transitions() -> None:
    assert can_transition_post(PostStatus.DRAFT, PostStatus.PROCESSING)
    assert not can_transition_post(PostStatus.POSTED, PostStatus.PROCESSING)


def test_session_transitions() -> None:
    assert can_transition_session(SessionState.REVIEW_READY, SessionState.AWAITING_CAPTION_EDIT)
    assert not can_transition_session(SessionState.IDLE, SessionState.AWAITING_POST_CONFIRMATION)
