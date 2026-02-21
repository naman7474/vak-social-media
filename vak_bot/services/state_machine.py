from __future__ import annotations

from vak_bot.enums import PostStatus, SessionState

_ALLOWED_POST_TRANSITIONS = {
    PostStatus.DRAFT: {PostStatus.PROCESSING, PostStatus.CANCELLED},
    PostStatus.PROCESSING: {PostStatus.REVIEW_READY, PostStatus.FAILED, PostStatus.CANCELLED},
    PostStatus.REVIEW_READY: {PostStatus.APPROVED, PostStatus.PROCESSING, PostStatus.CANCELLED},
    PostStatus.APPROVED: {PostStatus.POSTED, PostStatus.FAILED, PostStatus.CANCELLED},
    PostStatus.POSTED: set(),
    PostStatus.FAILED: {PostStatus.PROCESSING, PostStatus.CANCELLED},
    PostStatus.CANCELLED: set(),
}

_ALLOWED_SESSION_TRANSITIONS = {
    SessionState.IDLE: {SessionState.REVIEW_READY, SessionState.AWAITING_CAPTION_EDIT, SessionState.AWAITING_APPROVAL},
    SessionState.REVIEW_READY: {
        SessionState.AWAITING_CAPTION_EDIT,
        SessionState.AWAITING_APPROVAL,
        SessionState.IDLE,
    },
    SessionState.AWAITING_CAPTION_EDIT: {SessionState.REVIEW_READY, SessionState.IDLE},
    SessionState.AWAITING_APPROVAL: {SessionState.AWAITING_POST_CONFIRMATION, SessionState.REVIEW_READY, SessionState.IDLE},
    SessionState.AWAITING_POST_CONFIRMATION: {SessionState.IDLE, SessionState.REVIEW_READY},
}


def can_transition_post(current: PostStatus, target: PostStatus) -> bool:
    return target in _ALLOWED_POST_TRANSITIONS.get(current, set())


def can_transition_session(current: SessionState, target: SessionState) -> bool:
    return target in _ALLOWED_SESSION_TRANSITIONS.get(current, set())
