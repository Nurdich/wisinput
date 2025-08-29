#!/usr/bin/env python3
"""
WisInput 简化启动器
用于 uvx 直接运行，自动处理依赖和配置
"""

import os
import sys
import subprocess
import tempfile
import shutil
from pathlib import Path

def setup_environment():
    """设置运行环境"""
    # 设置默认环境变量
    os.environ.setdefault("TRANSCRIPTIONS_BUTTON", "alt_l")
    os.environ.setdefault("TRANSLATIONS_BUTTON", "alt_r") 
    os.environ.setdefault("SYSTEM_PLATFORM", "win")
    os.environ.setdefault("SERVICE_PLATFORM", "openai")  # 默认使用OpenAI服务
    os.environ.setdefault("FLOATING_WINDOW_MODE", "status")
    os.environ.setdefault("WAVE_GAIN", "15")
    os.environ.setdefault("INPUT_MODE", "type")
    
    print("🎤 WisInput - 智能语音输入工具")
    print("=" * 50)
    print("✅ 环境配置完成")
    print(f"📁 工作目录: {os.getcwd()}")
    print()
    print("🎯 快捷键:")
    print("  - 按住 Alt 键: 语音转录")
    print("  - 按住 右Alt 键: 语音翻译")
    print()
    print("⚙️ 当前配置:")
    print(f"  - 服务平台: {os.environ.get('SERVICE_PLATFORM', 'openai')}")
    print(f"  - 悬浮窗模式: {os.environ.get('FLOATING_WINDOW_MODE', 'status')}")
    print(f"  - 声纹增益: {os.environ.get('WAVE_GAIN', '15')}")
    print()

def check_api_key():
    """检查API密钥配置"""
    if os.environ.get("SERVICE_PLATFORM", "openai").lower() == "openai":
        if not os.environ.get("OPENAI_API_KEY"):
            print("⚠️  警告: 未检测到 OPENAI_API_KEY 环境变量")
            print("   请设置 OpenAI API 密钥或切换到本地模式:")
            print("   export OPENAI_API_KEY=your_api_key")
            print("   或者使用本地模式: export SERVICE_PLATFORM=local")
            print()

def main():
    """主启动函数"""
    try:
        setup_environment()
        check_api_key()
        
        print("🚀 正在启动 WisInput...")
        
        # 导入并运行主程序
        from .windows_app import main as app_main
        app_main()
        
    except ImportError as e:
        print(f"❌ 导入错误: {e}")
        print("请确保所有依赖已正确安装")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n👋 用户中断，程序退出")
        sys.exit(0)
    except Exception as e:
        print(f"❌ 启动失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
