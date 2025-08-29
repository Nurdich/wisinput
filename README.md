# WisInput - 智能语音输入工具 🎤

一个支持实时语音转录和翻译的AI助手，让你通过语音快速输入文本。

## ✨ 功能特性

- 🎤 **实时语音转录** - 按住 Alt 键说话，自动转录为文本
- 🌐 **实时语音翻译** - 按住 右Alt 键说话，自动翻译成英文
- 🎨 **美观悬浮窗** - 现代化的透明悬浮窗界面
- ⚡ **高性能AI模型** - 支持本地和云端AI模型
- 🔧 **自动模型下载** - 首次使用时自动下载所需模型
- 📋 **智能文本输入** - 自动优化和格式化文本

## 🚀 快速开始

### 安装

```bash
pip install wisinput
```

### 运行

```bash
wisinput
```

### 使用

1. **转录模式**：按住 `Alt` 键说话，松开后自动转录
2. **翻译模式**：按住 `右Alt` 键说话，松开后自动翻译成英文

## ⚙️ 配置

通过环境变量可以自定义配置：

```bash
# 快捷键配置
export TRANSCRIPTIONS_BUTTON="alt_l"    # 转录快捷键
export TRANSLATIONS_BUTTON="alt_r"      # 翻译快捷键

# 服务配置
export SERVICE_PLATFORM="local"         # 使用本地模型
export LOCAL_ASR_URL="http://localhost:8000"  # 本地服务地址

# 界面配置
export FLOATING_WINDOW_MODE="status"    # 悬浮窗模式
export WAVE_GAIN="15"                   # 声纹增益
```

## 🎯 系统要求

- Windows 10/11
- Python 3.12+
- 麦克风设备

## 📝 许可证

MIT License

## 🤝 贡献

欢迎提交 Issues 和 Pull Requests！
