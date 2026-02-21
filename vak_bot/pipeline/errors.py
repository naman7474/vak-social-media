class PipelineError(Exception):
    error_code = "pipeline_error"
    user_message = "Something went wrong. Please try again."


class DownloadError(PipelineError):
    error_code = "download_error"
    user_message = "Couldn't download that post. Try a different link or send me a screenshot instead."


class PrivatePostError(PipelineError):
    error_code = "private_or_deleted"
    user_message = "That post seems to be private or deleted. Can you try another one?"


class UnsupportedMediaError(PipelineError):
    error_code = "unsupported_media"
    user_message = "This looks like a reel/video. This bot handles image posts only."


class AnalysisError(PipelineError):
    error_code = "analysis_error"
    user_message = "Taking a bit longer than usual. Hang tight..."


class StylingError(PipelineError):
    error_code = "styling_error"
    user_message = "Styling is taking longer. Trying a different approach..."


class SareePreservationError(PipelineError):
    error_code = "saree_preservation_failed"
    user_message = "The styled image didn't look right. Let me try again with a different approach..."


class CaptionError(PipelineError):
    error_code = "caption_error"
    user_message = "Almost there, just polishing the caption..."


class PublishError(PipelineError):
    error_code = "publish_error"
    user_message = "Posting failed. I've saved your post — want me to try again or you can post manually?"
