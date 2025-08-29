import os
import time
from functools import wraps
import threading
from io import BytesIO

try:
 import dotenv
 import openai
 OPENAI_AVAILABLE = True
except ImportError:
 OPENAI_AVAILABLE = False
 openai = None


# Placeholder logger and translator
class logger:
    @staticmethod
    def info(msg): print(f"INFO: {msg}")
    @staticmethod
    def warning(msg): print(f"WARNING: {msg}")
    @staticmethod
    def error(msg): print(f"ERROR: {msg}")

class TranslateProcessor:
    def translate(self, text):
        return f"[翻译] {text}"  # 占位符翻译

if OPENAI_AVAILABLE:
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
 DEFAULT_TIMEOUT = 30
 DEFAULT_MODEL = os.getenv("OPENAI_ASR_MODEL", "whisper-1")

    def __init__(self):
        if not OPENAI_AVAILABLE:
 logger.warning("OpenAI 依赖不可用，语音转录将无法正常工作")
 self.openai_client = None
            self.timeout_seconds = self.DEFAULT_TIMEOUT
            self.model = self.DEFAULT_MODEL
            self.translate_processor = TranslateProcessor()
            return

 # 构造 OpenAI 客户端
 api_key = os.getenv("OPENAI_API_KEY")
 api_base = os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1")

 openai_client = None
        try:
            if api_key:
 openai_client = openai.OpenAI(api_key=api_key, base_url=api_base)
 logger.info("已启用 OpenAI API 模式")
            else:
 logger.warning("未检测到 OPENAI_API_KEY，云端转写将不可用")
        except Exception as e:
 logger.error(f"初始化 OpenAI 客户端失败: {e}")
 openai_client = None

        self.openai_client = openai_client
        self.timeout_seconds = self.DEFAULT_TIMEOUT
        self.model = self.DEFAULT_MODEL
        self.translate_processor = TranslateProcessor()
    
    @timeout_decorator(15)
    def _call_openai_asr(self, mode: str, audio_data, prompt: str):
        if not OPENAI_AVAILABLE:
            raise RuntimeError("OpenAI 依赖不可用")
        
        if not self.openai_client:
            raise RuntimeError("OpenAI 客户端未配置")

        # OpenAI ASR API 期望文件对象
        if isinstance(audio_data, bytes):
            audio_file = BytesIO(audio_data)
            audio_file.name = "audio.wav" # 必须有文件名
        elif isinstance(audio_data, BytesIO):
            audio_file = audio_data
            audio_file.name = "audio.wav" # 确保有文件名
        else:
            raise TypeError(f"audio_data 类型无效: {type(audio_data)}，需要 bytes 或 BytesIO")

        if mode == "transcriptions":
            response = self.openai_client.audio.transcriptions.create(
                model=self.model,
                file=audio_file,
                response_format="text",
                prompt=prompt if prompt else None,
            )
        elif mode == "translations":
            response = self.openai_client.audio.translations.create(
                model=self.model,
                file=audio_file,
                response_format="text",
                prompt=prompt if prompt else None,
            )
        else:
            raise ValueError(f"不支持的模式: {mode}")
        
        return response.text.strip()
    
    def process_audio(self, audio_buffer: bytes, mode: str = "transcriptions", prompt: str = ""):
        if not OPENAI_AVAILABLE or not self.openai_client:
            # 返回占位符结果
            return f"[{mode}] 语音转录功能不可用（缺少配置或依赖）", None

        try:
            start = time.time()
            logger.info(f"正在调用 OpenAI ASR... (模式: {mode})")
            result = self._call_openai_asr(mode, audio_buffer, prompt)
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