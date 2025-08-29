"""
WisInput - 智能语音输入工具
一个支持实时语音转录和翻译的AI助手

快捷键：
- 按住 Alt 键：实时语音转录（保持原文）
- 按住 右Alt 键：实时语音翻译（翻译成英文）

使用方法：
1. 安装: pip install wisinput
2. 运行: wisinput
3. 转录模式：按住 Alt 键说话，松开自动转录
4. 翻译模式：按住 右Alt 键说话，松开自动翻译成英文

功能特性：
- 🎤 实时语音转录
- 🌐 实时语音翻译
- 🎨 美观的悬浮窗界面
- ⚡ 高性能本地/云端AI模型
- 🔧 自动模型下载
- 📋 智能文本输入
"""

__version__ = "0.1.0"
__author__ = "wisinput"
__email__ = "wisinput@example.com"

# 导出主要功能
from .windows_app import main

__all__ = ["main"] 