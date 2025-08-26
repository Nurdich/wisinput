import os
import time
from functools import wraps
import threading
from io import BytesIO

import dotenv
from google import genai
from google.genai import types

from ..llm.translate import TranslateProcessor
from ..utils.logger import logger

dotenv.load_dotenv()


def timeout_decorator(seconds):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            result = [None]
            error = [None]
            completed = threading.Event()

            def target():
                try:
                    result[0] = func(*args, **kwargs)
                except Exception as e:
                    error[0] = e
                finally:
                    completed.set()

            thread = threading.Thread(target=target)
            thread.daemon = True
            thread.start()

            if completed.wait(seconds):
                if error[0] is not None:
                    raise error[0]
                return result[0]
            raise TimeoutError(f"操作超时 ({seconds}秒)")

        return wrapper
    return decorator


class GoogleAiProcessor:
    DEFAULT_TIMEOUT = 20
    DEFAULT_MODEL = os.getenv("GEMINI_ASR_MODEL", "gemini-2.5-flash")

    def __init__(self):
        # 构造 Google GenAI 客户端（支持 Vertex 或 API Key）
        use_vertex_ai = os.getenv("GEMINI_USE_VERTEXAI", "false").lower() == "true"
        vertex_project = os.getenv("VERTEX_PROJECT", "")
        vertex_location = os.getenv("VERTEX_LOCATION", "global")
        api_key = os.getenv("GEMINI_API_KEY")

        google_client = None
        try:
            if use_vertex_ai and vertex_project:
                google_client = genai.Client(vertexai=True, project=vertex_project, location=vertex_location)
                logger.info(f"已启用 Vertex AI（project={vertex_project}, location={vertex_location}）")
            elif api_key:
                google_client = genai.Client(api_key=api_key)
                logger.info("已启用 Gemini API Key 模式")
            else:
                logger.warning("未检测到 GEMINI_API_KEY 或 Vertex 配置，云端转写将不可用")
        except Exception as e:
            logger.error(f"初始化 Google/Gemini 客户端失败: {e}")
            google_client = None

        self.google_client = google_client
        self.timeout_seconds = self.DEFAULT_TIMEOUT
        self.model = self.DEFAULT_MODEL
        self.translate_processor = TranslateProcessor()
    @timeout_decorator(15)
    def _call_google_asr(self, mode: str, audio_data, prompt: str):
        if not self.google_client:
            raise RuntimeError("Google 客户端未配置")

        # 统一转成 bytes
        if isinstance(audio_data, BytesIO):
            audio_bytes = audio_data.getvalue()
        elif isinstance(audio_data, (bytes, bytearray)):
            audio_bytes = bytes(audio_data)
        else:
            raise TypeError(f"audio_data 类型无效: {type(audio_data)}，需要 bytes 或 BytesIO")

        parts = [types.Part.from_bytes(data=audio_bytes, mime_type="audio/wav")]
        if prompt:
            parts.insert(0, types.Part.from_text(prompt))

        response = self.google_client.models.generate_content(
            model=self.model,
            contents=parts,
            config=types.GenerateContentConfig(
                response_mime_type="text/plain",
                temperature=0.2,
                top_p=0.9,
            ),
        )
        return str(response.text or "").strip()
    def process_audio(self, audio_buffer: bytes, mode: str = "transcriptions", prompt: str = ""):
        try:
            start = time.time()
            logger.info(f"正在调用 Google ASR... (模式: {mode})")
            result = self._call_google_asr(mode, audio_buffer, prompt)
            logger.info(f"API 调用成功 ({mode}), 耗时: {time.time() - start:.1f}s")

            if mode == "translations" and result:
                result = self.translate_processor.translate(result)

            logger.info(f"识别结果: {result}")
            return result, None
        except TimeoutError:
            error_msg = f"❌ API 请求超时 ({self.timeout_seconds}秒)"
            logger.error(error_msg)
            return None, error_msg
        except Exception as e:
            error_msg = f"❌ {str(e)}"
            logger.error(f"音频处理错误: {str(e)}", exc_info=True)
            return None, error_msg

