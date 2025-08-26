import dotenv
import os
import requests
import json
from ..utils.logger import logger


dotenv.load_dotenv()

class SymbolProcessor:
    def __init__(self, service_platform=None):
        # 如果没有指定平台，从环境变量获取
        if service_platform is None:
            service_platform = os.getenv("SERVICE_PLATFORM", "google")

        self.service_platform = service_platform.lower()

        # 使用原生 HTTP API 调用 Gemini
        self.api_key = os.getenv("GEMINI_API_KEY")
        self.api_base_url = "https://generativelanguage.googleapis.com/v1beta"
        
        if not self.api_key:
            logger.warning("未检测到 GEMINI_API_KEY，优化功能可能不可用")
        else:
            logger.info("已启用 Gemini REST API 模式")

        # 统一走 Google 优化
        self.service_platform = "google"

        # 优化相关可配置参数（环境变量覆盖）
        self.optimize_model = os.getenv("GEMINI_OPTIMIZE_MODEL", "gemini-2.0-flash")
        try:
            self.optimize_temperature = float(os.getenv("OPTIMIZE_TEMPERATURE", "0.2"))
        except ValueError:
            self.optimize_temperature = 0.2
        try:
            self.optimize_top_p = float(os.getenv("OPTIMIZE_TOP_P", "0.9"))
        except ValueError:
            self.optimize_top_p = 0.9

    def optimize_result(self, text):
        """优化识别结果，纠正错误并改进文本质量"""
        return self.optimize_result_with_google_ai(text)

    def optimize_result_with_google_ai(self, text):
        # 检查 API Key 是否可用
        if not self.api_key:
            logger.warning("优化功能不可用，返回原文本")
            return text
        # 规则：
        # 1. 修正明显的听写/拼写/用词错误与错别字。
        # 2. 自动补全并规范标点（中英文空格与全半角）；合并重复字符与口头语（例如："嗯"、"啊"、"然后然后"）。
        # 3. 统一数字：将中文数字转换为阿拉伯数字；保留时间、日期、金额、量词等常见格式。
        # 4. 规范英文大小写与专有名词；保持缩写与技术术语（如 API、GPU、C#）。
        # 5. 若英文句子中出现中文谐音导致的误拼（如"到奈特"），改为正确英文（如"tonight"）。仅做该类纠正，不做中英双语对照。
        # 6. 不改变句子含义，不增删信息，不进行主观改写或过度润色风格。
        # 7. 不翻译整段文本（除第5条的谐音纠正），不回答问题，不添加解释、前后缀或任何元信息。
        # 8. 只输出优化后的最终文本，去除首尾空白。

        system_prompt = """
        你是一个语音转写后处理与润色助手。目标：在严格保持原始语义与事实不变的前提下，使文本更清晰、规范、精炼。
        规则：
        转述我跟你说的话意思简明要简可以不用和原话一样但是一定要简单要简我说的包括发了一些口气音还有一些口语尽量把它删掉让文字看起来又像人说的但是又是打字的那个什么打字打出来的
        不是解释是转述
        1. 修正明显的听写/拼写/用词错误与错别字。
        2. 自动补全并规范标点（中英文空格与全半角）；合并重复字符与口头语（例如："嗯"、"啊"、"然后然后"）。
        3. 统一数字：将中文数字转换为阿拉伯数字；保留时间、日期、金额、量词等常见格式。
        4. 规范英文大小写与专有名词；保持缩写与技术术语（如 API、GPU、C#）。
        5. 若英文句子中出现中文谐音导致的误拼（如"到奈特"），改为正确英文（如"tonight"）。仅做该类纠正，不做中英双语对照。
        6. 不改变句子含义，不增删信息，不进行主观改写或过度润色风格。
        7. 不翻译整段文本（除第5条的谐音纠正），不回答问题，不添加解释、前后缀或任何元信息。
        8. 只输出优化后的最终文本，去除首尾空白

        输出格式：纯文本，句读自然，必要时可将过长句子拆分为多句。
        """

        # 构建请求数据
        payload = {
            "contents": [
                {
                    "parts": [
                        {
                            "text": text
                        }
                    ]
                }
            ],
            "generationConfig": {
                "temperature": self.optimize_temperature,
                "topP": self.optimize_top_p,
                "responseMimeType": "text/plain"
            },
            "systemInstruction": {
                "parts": [
                    {
                        "text": system_prompt
                    }
                ]
            }
        }

        try:
            # 发送 HTTP 请求
            url = f"{self.api_base_url}/models/{self.optimize_model}:generateContent"
            headers = {
                "Content-Type": "application/json",
                "X-goog-api-key": self.api_key
            }
            
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()
            
            result = response.json()
            
            # 解析响应
            if "candidates" in result and len(result["candidates"]) > 0:
                candidate = result["candidates"][0]
                if "content" in candidate and "parts" in candidate["content"]:
                    parts = candidate["content"]["parts"]
                    if len(parts) > 0 and "text" in parts[0]:
                        return parts[0]["text"].strip()
            
            logger.warning("API 响应格式异常，返回原文本")
            return text

        except requests.exceptions.RequestException as e:
            logger.error(f"HTTP 请求失败: {e}")
            return text
        except Exception as e:
            logger.error(f"优化识别结果失败: {e}")
            # 如果是API密钥权限问题，记录详细错误信息
            if "401" in str(e) or "403" in str(e):
                logger.error("API密钥权限不足，请检查密钥是否有效")
            return text