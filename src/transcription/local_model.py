import os
import threading
import time
from functools import wraps

import dotenv
import httpx

from src.llm.translate import TranslateProcessor
from src.llm.symbol import SymbolProcessor
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

class LocalModelProcessor:
    # 类级别的配置参数
    DEFAULT_TIMEOUT = 20  # API 超时时间（秒）
    DEFAULT_BASE_URL = "http://192.168.1.142:8000"
    DEFAULT_MODEL = "k1nto/Belle-whisper-large-v3-zh-punct-ct2"

    def __init__(self):
        # 从环境变量获取本地服务器配置
        self.base_url = os.getenv("LOCAL_MODEL_BASE_URL", self.DEFAULT_BASE_URL)
        self.timeout_seconds = int(os.getenv("LOCAL_MODEL_TIMEOUT", str(self.DEFAULT_TIMEOUT)))
        self.model = os.getenv("LOCAL_MODEL_NAME", self.DEFAULT_MODEL)

        # 功能配置
        self.convert_to_simplified = os.getenv("CONVERT_TO_SIMPLIFIED", "false").lower() == "true"

        # 初始化处理器
        self.translate_processor = TranslateProcessor()

        # 统一使用 Google/Gemini 做标点与优化（需 GEMINI_API_KEY 或 Vertex 配置）
        self.symbol_processor = SymbolProcessor(service_platform="google")
        if not os.getenv("GEMINI_API_KEY") and os.getenv("GEMINI_USE_VERTEXAI", "false").lower() != "true":
            logger.warning("未检测到 GEMINI_API_KEY/Vertex 配置，标点与优化可能不可用")

        logger.info(f"本地模型处理器初始化完成，服务器地址: {self.base_url}, 模型: {self.model}")

    def _convert_traditional_to_simplified(self, text):
        """将繁体中文转换为简体中文"""
        if not self.convert_to_simplified or not text:
            return text
        # 注意：这里需要OpenCC库，如果需要可以添加
        try:
            from opencc import OpenCC
            cc = OpenCC('t2s')
            return cc.convert(text)
        except ImportError:
            logger.warning("OpenCC库未安装，无法转换繁体中文")
            return text

    @timeout_decorator(20)
    def _call_local_api(self, audio_data, prompt: str = "Translate what I say into English:"):
        """调用本地模型 API"""
        transcription_url = f"{self.base_url}/v1/audio/transcriptions"

        # 仅音频走 files，文本参数走 data
        files = {
            'file': ('audio.wav', audio_data),
            'type': 'audio/wav',
        }
        data = {
            'model': self.model,
            
        }
        if prompt:
            data['prompt'] = prompt

        # 可以添加额外的headers如果本地服务需要
        headers = {}
        auth_token = os.getenv("LOCAL_MODEL_AUTH_TOKEN")
        if auth_token:
            headers['Authorization'] = f"Bearer {auth_token}"

        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                logger.info(f"正在向本地服务器发送请求: {transcription_url} (包含提示词: {bool(prompt)})")
                response = client.post(transcription_url, files=files, data=data, headers=headers)
                response.raise_for_status()
                
                # 尝试解析JSON响应
                try:
                    result = response.json()
                    # 支持多种响应格式
                    if isinstance(result, dict):
                        # 标准OpenAI格式
                        if 'text' in result:
                            return result['text']
                        # 其他可能的格式
                        elif 'transcription' in result:
                            return result['transcription']
                        elif 'result' in result:
                            return result['result']
                        else:
                            logger.warning(f"未知的响应格式: {result}")
                            return str(result)
                    else:
                        return str(result)
                except Exception as json_error:
                    # 如果不是JSON，直接返回文本
                    logger.warning(f"响应不是有效JSON，返回原始文本: {json_error}")
                    return response.text.strip()
                    
        except httpx.ConnectError as e:
            logger.error(f"无法连接到本地服务器 {self.base_url}: {e}")
            raise Exception(f"无法连接到本地服务器，请确保服务正在运行在 {self.base_url}")
        except httpx.TimeoutException as e:
            logger.error(f"请求超时: {e}")
            raise Exception(f"请求超时 ({self.timeout_seconds}秒)")
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP错误 {e.response.status_code}: {e.response.text}")
            raise Exception(f"服务器返回错误: {e.response.status_code}")

    def process_audio(self, audio_buffer, mode="transcriptions", prompt=""):
        """处理音频（转录或翻译）
        
        Args:
            audio_buffer: 音频数据缓冲
            mode: 'transcriptions' 或 'translations'，决定是转录还是翻译
            prompt: 提示词（本地模型可能不支持）
        
        Returns:
            tuple: (结果文本, 错误信息)
            - 如果成功，错误信息为 None
            - 如果失败，结果文本为 None
        """
        try:
            start_time = time.time()
            
            logger.info(f"正在调用本地模型 API... (模式: {mode})")
            # 透传提示词
            result = self._call_local_api(audio_buffer, prompt="Translate what I say into English:")

            logger.info(f"本地模型 API 调用成功 ({mode}), 耗时: {time.time() - start_time:.1f}秒")
            
            # 转换繁体到简体
            result = self._convert_traditional_to_simplified(result)

            # 如果是翻译模式，使用翻译处理器
            if mode == "translations":
                result = self.translate_processor.translate(result)

            logger.info(f"识别结果: {result}")

 
            result = self.symbol_processor.optimize_result(result)
            logger.info(f"优化结果: {result}")

            return result, None

        except Exception as e:
            error_msg = f"本地模型处理失败: {str(e)}"
            logger.error(error_msg)
            return None, error_msg

    def test_connection(self):
        """测试与本地服务器的连接"""
        try:
            with httpx.Client(timeout=5) as client:
                # 尝试访问健康检查端点或根路径
                health_url = f"{self.base_url}/health"
                try:
                    response = client.get(health_url)
                    if response.status_code == 200:
                        logger.info("本地服务器连接测试成功 (health endpoint)")
                        return True
                except:
                    # 如果没有health端点，尝试根路径
                    response = client.get(self.base_url)
                    logger.info(f"本地服务器连接测试成功 (status: {response.status_code})")
                    return True
        except Exception as e:
            logger.error(f"本地服务器连接测试失败: {e}")
            return False
