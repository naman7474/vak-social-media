from __future__ import annotations

import re
from dataclasses import dataclass

from vak_bot.enums import CallbackAction

CALLBACK_PATTERN = re.compile(
    r"^post:(?P<post_id>\d+):variant:(?P<variant>\d+):action:(?P<action>select|approve|redo|cancel|edit_caption|select_video|extend|reel_this)$"
)


@dataclass
class ParsedCallback:
    post_id: int
    variant: int
    action: CallbackAction


def make_callback(post_id: int, variant: int, action: CallbackAction) -> str:
    return f"post:{post_id}:variant:{variant}:action:{action.value}"


def parse_callback(data: str) -> ParsedCallback | None:
    if not data:
        return None
    match = CALLBACK_PATTERN.match(data)
    if not match:
        return None
    return ParsedCallback(
        post_id=int(match.group("post_id")),
        variant=int(match.group("variant")),
        action=CallbackAction(match.group("action")),
    )
