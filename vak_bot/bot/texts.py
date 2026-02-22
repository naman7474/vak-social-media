UNAUTHORIZED_MESSAGE = "This bot is private. Visit vakstudios.in to shop."

WELCOME_MESSAGE = (
    "Welcome to the Vâk posting bot.\n\n"
    "Send an Instagram/Pinterest inspiration link with saree photo(s), or send a link + product code (e.g. VAK-042)."
)

HELP_MESSAGE = (
    "How to use:\n"
    "1) Send inspiration link + saree photo(s)\n"
    "2) Or send link + product code (VAK-042)\n"
    "3) Review options and reply: 1/2/3, edit caption, redo, redo close-up, approve, cancel\n"
    "4) After approve, reply post now\n\n"
    "Commands:\n"
    "/reel <link> [VAK-XXX] (force reel mode)\n"
    "/recent, /queue, /reelqueue\n"
    "/products, /stats, /cancel <post_id>\n\n"
    "Note: scheduling is not in v1 yet."
)

PROCESSING_MESSAGE = (
    "Got it! Analyzing the reference post and styling your saree.\n"
    "This usually takes 2-3 minutes. I'll send you options when ready."
)

NEED_PHOTO_MESSAGE = "Got the inspiration! Now send me the saree photo(s) you want to feature."
UNSUPPORTED_LINK_MESSAGE = "I work best with Instagram and Pinterest links. Can you send one of those?"
V1_SCHEDULING_MESSAGE = "Scheduling is not available in v1 yet. Please use 'post now'."

REEL_DETECTED_MESSAGE = (
    "🎬 That's a Reel! I'll create a video version of your saree.\n"
    "This takes ~5 minutes (styling + video generation). I'll send preview options when ready."
)

VIDEO_PROCESSING_MESSAGE = (
    "Styling the start frame first, then animating with Veo 3.1.\n"
    "This usually takes 4-6 minutes. I'll send you a video preview."
)

VIDEO_EXTENDING_MESSAGE = "Extending video by 8 seconds. This takes ~3 minutes..."
