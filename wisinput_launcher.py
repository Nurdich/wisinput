#!/usr/bin/env python3
"""
WisInput 启动器
简化的启动脚本，可以直接运行
"""

import sys
import os

# 添加当前目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 导入并运行主程序
try:
    from src.windows_app import main
    main()
except ImportError as e:
    print(f"导入错误: {e}")
    print("请确保所有依赖已安装: uv sync")
    sys.exit(1)
except Exception as e:
    print(f"启动失败: {e}")
    sys.exit(1)
