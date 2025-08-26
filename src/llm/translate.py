import os
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

class TranslateProcessor:
    def __init__(self):
        use_vertex_ai = os.getenv("GEMINI_USE_VERTEXAI", "false").lower() == "true"
        vertex_project = os.getenv("VERTEX_PROJECT", "")
        vertex_location = os.getenv("VERTEX_LOCATION", "global")
        api_key = os.getenv("GEMINI_API_KEY")

        client = None
        try:
            if use_vertex_ai and vertex_project:
                client = genai.Client(vertexai=True, project=vertex_project, location=vertex_location)
            elif api_key:
                client = genai.Client(api_key=api_key)
        except Exception:
            client = None

        self.client = client
        self.model = os.getenv("GEMINI_TRANSLATE_MODEL", "gemini-2.0-flash")

    def translate(self, text: str) -> str:
        if not text:
            return text
        if not self.client:
            return text

        system_prompt = (
            "You are a translation assistant. Translate the user's input into English. "
            "Only output the translated text."
        )

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=[
                    types.Part.from_text(system_prompt),
                    types.Part.from_text(text),
                ],
                config=types.GenerateContentConfig(
                    response_mime_type="text/plain",
                    temperature=0.2,
                    top_p=0.9,
                ),
            )
            return str(response.text or "").strip()
        except Exception:
            return text