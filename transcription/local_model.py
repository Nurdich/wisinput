import os
import requests
import time
from io import BytesIO

# Placeholder logger
class logger:
    @staticmethod
    def info(msg): print(f"INFO: {msg}")
    @staticmethod
    def warning(msg): print(f"WARNING: {msg}")
    @staticmethod
    def error(msg): print(f"ERROR: {msg}")


class LocalModelProcessor:
    def __init__(self):
        self.base_url = os.getenv("LOCAL_ASR_URL", "http://localhost:8000")
        self.timeout = int(os.getenv("LOCAL_ASR_TIMEOUT", "30"))
        logger.info(f"本地模型处理器初始化完成 (URL: {self.base_url})")

    def process_audio(self, audio_buffer, mode: str = "transcriptions", prompt: str = ""):
        """处理音频，返回转录或翻译结果"""
        try:
            start_time = time.time()
            logger.info(f"正在调用本地ASR服务... (模式: {mode})")
            
            # 准备文件数据
            if isinstance(audio_buffer, BytesIO):
                audio_data = audio_buffer.getvalue()
            else:
                audio_data = audio_buffer
            
            files = {'file': ('audio.wav', audio_data, 'audio/wav')}
            
            # 准备表单数据
            data = {
                'mode': mode,
                'prompt': prompt if prompt else ''
            }
            
            # 发送请求
            endpoint = f"{self.base_url}/v1/audio/{mode}"
            response = requests.post(
                endpoint,
                files=files,
                data=data,
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                result = response.json()
                text = result.get('text', '').strip()
                
                elapsed = time.time() - start_time
                logger.info(f"本地ASR调用成功 ({mode}), 耗时: {elapsed:.1f}s")
                logger.info(f"识别结果: {text}")
                
                return text, None
            else:
                error_msg = f"❌ 本地ASR服务错误: HTTP {response.status_code}"
                logger.error(error_msg)
                try:
                    error_detail = response.json().get('detail', 'Unknown error')
                    error_msg += f" - {error_detail}"
                except:
                    pass
                return None, error_msg
                
        except requests.exceptions.ConnectionError:
            error_msg = "❌ 无法连接到本地ASR服务，请确认服务已启动"
            logger.error(error_msg)
            return None, error_msg
        except requests.exceptions.Timeout:
            error_msg = f"❌ 本地ASR服务请求超时 ({self.timeout}秒)"
            logger.error(error_msg)
            return None, error_msg
        except Exception as e:
            error_msg = f"❌ 本地ASR处理失败: {str(e)}"
            logger.error(f"本地模型处理错误: {str(e)}", exc_info=True)
            return None, error_msg