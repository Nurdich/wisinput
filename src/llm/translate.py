import os
from dotenv import load_dotenv

try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    openai = None

load_dotenv()

class TranslateProcessor:
    def __init__(self):
        if not OPENAI_AVAILABLE:
            self.client = None
            return
            
        # 使用Google AI的API密钥和基础URL
        api_key = os.getenv("GEMINI_API_KEY")
        # Google AI的OpenAI兼容端点
        api_base = os.getenv("GEMINI_API_BASE", "https://generativelanguage.googleapis.com/v1beta/openai/")
        
        client = None
        try:
            if api_key:
                client = openai.OpenAI(
                    api_key=api_key,
                    base_url=api_base
                )
        except Exception:
            client = None

        self.client = client
        self.model = os.getenv("GEMINI_TRANSLATE_MODEL", "gemini-2.0-flash-exp")

    def translate(self, text: str) -> str:
        if not text:
            return text
        if not self.client or not OPENAI_AVAILABLE:
            return text

        system_prompt = (
            "You are a translation assistant. Translate the user's input into English. "
            "Only output the translated text."
        )

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": text}
                ],
                temperature=0.2,
                top_p=0.9,
                max_tokens=1000
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"翻译错误: {e}")
            return text