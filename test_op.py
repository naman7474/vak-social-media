from google import genai
import os

client = genai.Client()
op_name = "operations/44yna6jwboty"
operation = client.operations.get(operation=op_name)

print("operation.done:", operation.done)
print("operation.error:", operation.error)
print("operation.response:", operation.response)

if operation.response:
    print("generated_videos:", getattr(operation.response, "generated_videos", None))
    print("rai_count:", getattr(operation.response, "rai_media_filtered_count", None))
    print("rai_reasons:", getattr(operation.response, "rai_media_filtered_reasons", None))
