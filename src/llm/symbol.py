import dotenv
import os
import requests
from typing import Optional
from ..utils.logger import logger


dotenv.load_dotenv()

# 系统提示词常量
_SYSTEM_PROMPT = """你是一个语音转写后处理与润色助手。请直接对输入的文本进行优化处理，不要回答问题或进行解释。

规则：
1. 修正明显的听写/拼写/用词错误与错别字。
2. 自动补全并规范标点（中英文空格与全半角）；合并重复字符与口头语（例如："嗯"、"啊"、"然后然后"）。
3. 统一数字：将中文数字转换为阿拉伯数字；保留时间、日期、金额、量词等常见格式。
4. 规范英文大小写与专有名词；保持缩写与技术术语（如 API、GPU、C#）。
5. 若英文句子中出现中文谐音导致的误拼（如"到奈特"），改为正确英文（如"tonight"）。
6. 不改变句子含义，不增删信息，不进行主观改写。
7. 不翻译文本，不添加任何解释或额外信息。
8. 直接返回优化后的文本内容，不要有任何其他回应。

严格遵守：仅输出优化后的文本，不要有任何其他对话或解释性内容。"""

# 默认配置常量
_DEFAULT_MODEL = "gpt-4.1-mini"
_DEFAULT_TEMPERATURE = 0.1
_DEFAULT_TOP_P = 0.9
_DEFAULT_TIMEOUT = 30


class SymbolProcessor:
    """使用 OpenAI REST API 对语音转写的文本进行后处理和优化。"""

    def __init__(self, service_platform: Optional[str] = None):
        """
        初始化 SymbolProcessor。

        Args:
            service_platform: 服务平台，目前统一使用 OpenAI
        """
        # 使用原生 HTTP API 调用 OpenAI
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.api_base_url = "https://api.openai.com/v1"

        if not self.api_key:
            logger.warning("未检测到 OPENAI_API_KEY，优化功能将不可用")
        else:
            logger.info("已启用 OpenAI REST API 模式")

        # 统一使用 OpenAI 优化
        self.service_platform = "openai"

        # 优化相关可配置参数（环境变量覆盖）
        self.optimize_model = os.getenv("OPENAI_OPTIMIZE_MODEL", _DEFAULT_MODEL)
        self.optimize_temperature = self._get_float_env("OPTIMIZE_TEMPERATURE", _DEFAULT_TEMPERATURE)
        self.optimize_top_p = self._get_float_env("OPTIMIZE_TOP_P", _DEFAULT_TOP_P)
        self.timeout = self._get_int_env("OPENAI_TIMEOUT", _DEFAULT_TIMEOUT)

    def _get_float_env(self, key: str, default: float) -> float:
        """安全地从环境变量获取浮点数值。"""
        try:
            return float(os.getenv(key, str(default)))
        except (ValueError, TypeError):
            logger.warning(f"环境变量 {key} 值无效，使用默认值 {default}")
            return default

    def _get_int_env(self, key: str, default: int) -> int:
        """安全地从环境变量获取整数值。"""
        try:
            return int(os.getenv(key, str(default)))
        except (ValueError, TypeError):
            logger.warning(f"环境变量 {key} 值无效，使用默认值 {default}")
            return default

    def optimize_result(self, text: str) -> str:
        """
        优化识别结果，纠正错误并改进文本质量。

        Args:
            text: 原始识别文本

        Returns:
            优化后的文本；如果优化失败或未配置，则返回原始文本
        """
        return self.optimize_result_with_openai(text)

    def optimize_result_with_openai(self, text: str) -> str:
        """
        使用 OpenAI API 优化文本。

        Args:
            text: 待优化的文本

        Returns:
            优化后的文本
        """
        # 检查 API Key 是否可用
        if not self.api_key:
            logger.warning("优化功能不可用，返回原文本")
            return text

        # 输入验证
        if not text or not text.strip():
            logger.info("输入文本为空，无需优化")
            return ""

        # 构建请求数据
        payload = {
            "model": self.optimize_model,
            "messages": [
                {
                    "role": "system",
                    "content": _SYSTEM_PROMPT
                },
                {
                    "role": "user",
                    "content": text
                }
            ],
            "temperature": self.optimize_temperature,
            "top_p": self.optimize_top_p
        }

        try:
            # 发送 HTTP 请求
            url = f"{self.api_base_url}/chat/completions"
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"
            }

            response = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
            response.raise_for_status()

            result = response.json()

            # 解析响应
            optimized_text = self._extract_text_from_response(result)
            if optimized_text is not None:
                return optimized_text

            logger.warning("API 响应格式异常，返回原文本")
            return text

        except requests.exceptions.Timeout:
            logger.error(f"API 请求超时 ({self.timeout}秒)，返回原文本")
            return text
        except requests.exceptions.HTTPError as e:
            logger.error(f"API HTTP 错误: {e.response.status_code} - {e.response.text}")
            return text
        except requests.exceptions.RequestException as e:
            logger.error(f"API 请求失败: {e}")
            return text
        except Exception as e:
            logger.error(f"优化文本时发生未知错误: {e}")
            return text

    def _extract_text_from_response(self, result: dict) -> Optional[str]:
        """
        从 API 响应中提取文本内容。

        Args:
            result: API 响应的 JSON 数据

        Returns:
            提取的文本内容，如果提取失败则返回 None
        """
        try:
            if "choices" in result and len(result["choices"]) > 0:
                choice = result["choices"][0]
                if "message" in choice and "content" in choice["message"]:
                    return choice["message"]["content"].strip()
            return None
        except (KeyError, IndexError, TypeError) as e:
            logger.error(f"解析 API 响应时出错: {e}")
            return None