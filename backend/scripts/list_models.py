from google import genai
from app.config import get_settings
client = genai.Client(api_key=get_settings().GEMINI_API_KEY)
models = [m.name for m in client.models.list() if 'gemini' in m.name.lower()]
print('AVAILABLE GEMINI MODELS:')
for m in models:
    print(' -', m)
