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
    REEL = "reel"


class VideoType(str, Enum):
    FABRIC_FLOW = "fabric-flow"
    CLOSE_UP = "close-up"
    LIFESTYLE = "lifestyle"
    REVEAL = "reveal"


class SessionState(str, Enum):
    IDLE = "idle"
    AWAITING_PHOTOS = "awaiting_photos"
    REVIEW_READY = "review_ready"
    AWAITING_CAPTION_EDIT = "awaiting_caption_edit"
    AWAITING_APPROVAL = "awaiting_approval"
    AWAITING_POST_CONFIRMATION = "awaiting_post_confirmation"
    AWAITING_VIDEO_SELECTION = "awaiting_video_selection"


class JobStage(str, Enum):
    INTAKE = "intake"
    DOWNLOAD = "download"
    ANALYZE = "analyze"
    STYLE = "style"
    VALIDATE = "validate"
    VIDEO_GENERATE = "video_generate"
    VIDEO_EXTEND = "video_extend"
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
    SELECT_VIDEO = "select_video"
    EXTEND = "extend"
    REEL_THIS = "reel_this"
