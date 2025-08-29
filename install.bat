@echo off
echo 正在安装 WisInput 智能语音输入工具...
echo.

REM 检查是否有 uv
where uv >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo 错误: 未找到 uv 工具
    echo 请先安装 uv: https://docs.astral.sh/uv/getting-started/installation/
    pause
    exit /b 1
)

REM 同步依赖
echo 正在安装依赖...
uv sync

REM 创建快捷方式脚本
echo @echo off > wisinput.bat
echo cd /d "%~dp0" >> wisinput.bat
echo uv run wisinput_launcher.py >> wisinput.bat

echo.
echo ✅ 安装完成！
echo.
echo 使用方法：
echo   1. 双击运行 wisinput.bat
echo   2. 或者在命令行运行: uv run wisinput_launcher.py
echo.
echo 快捷键：
echo   - 按住 Alt 键：语音转录
echo   - 按住 右Alt 键：语音翻译
echo.
pause
