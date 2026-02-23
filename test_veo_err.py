from google import genai
from vak_bot.config import get_settings

settings = get_settings()
api_key = settings.google_api_key or settings.gemini_api_key
client = genai.Client(api_key=api_key)

op_name = "operations/44yna6jwboty"
class DummyOp:
    def __init__(self, name):
        self.name = name

operation = client.operations.get(operation=DummyOp(op_name))

print("operation.done:", getattr(operation, "done", None))
print("operation.error:", getattr(operation, "error", None))
print("operation.response:", getattr(operation, "response", None))

if getattr(operation, "response", None):
    resp = operation.response
    print("generated_videos:", getattr(resp, "generated_videos", None))
    print("rai_count:", getattr(resp, "rai_media_filtered_count", None))
    print("rai_reasons:", getattr(resp, "rai_media_filtered_reasons", None))
