from enum import Enum


class PostStatus(str, Enum):
    DRAFT = "draft"
    PROCESSING = "processing"
    REVIEW_READY = "review_ready"
    APPROVED = "approved"
    POSTED = "posted"
    FAILED = "failed"
    CANCELLED = "cancelled"


class MediaType(str, Enum):
    SINGLE = "single"
    CAROUSEL = "carousel"


class SessionState(str, Enum):
    IDLE = "idle"
    REVIEW_READY = "review_ready"
    AWAITING_CAPTION_EDIT = "awaiting_caption_edit"
    AWAITING_APPROVAL = "awaiting_approval"
    AWAITING_POST_CONFIRMATION = "awaiting_post_confirmation"


class JobStage(str, Enum):
    INTAKE = "intake"
    DOWNLOAD = "download"
    ANALYZE = "analyze"
    STYLE = "style"
    VALIDATE = "validate"
    CAPTION = "caption"
    REVIEW = "review"
    POST = "post"
    CLEANUP = "cleanup"
    TOKEN_REFRESH = "token_refresh"


class JobStatus(str, Enum):
    STARTED = "started"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class CallbackAction(str, Enum):
    SELECT = "select"
    APPROVE = "approve"
    REDO = "redo"
    CANCEL = "cancel"
    EDIT_CAPTION = "edit_caption"
