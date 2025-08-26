# Whisper Input

Windows 托盘应用，支持语音输入功能，可将语音实时转换为文本并自动输入到光标位置。

## 功能特点

- 系统托盘运行，不占用任务栏空间
- 支持快捷键一键录音和转录
- 支持云端 (Google Gemini) 和本地模型两种转录方式
- 可选悬浮窗显示录音状态和结果
- 支持中英文翻译功能

## 安装和运行

使用 uvx 直接运行：

```bash
# 如果包已发布到 PyPI
uvx whisper-input

# 或者从本地源码运行
uvx --from . whisper-input
```

构建并安装到本地环境：

```bash
# 构建包
uv build

# 安装到本地环境
pip install .

# 然后可以直接运行
whisper-input
```

## 配置

首次运行前，请复制 `.env.example` 为 `.env` 并根据需要修改配置：

```bash
cp .env.example .env
```

主要配置项：

- `SERVICE_PLATFORM`: 选择服务提供商 (google|local)
- `GEMINI_API_KEY`: Google Gemini API 密钥 (使用云端服务时需要)
- `LOCAL_MODEL_BASE_URL`: 本地模型服务地址 (使用本地模型时需要)
- `TRANSCRIPTIONS_BUTTON`: 转录快捷键
- `TRANSLATIONS_BUTTON`: 翻译快捷键

## 快捷键

默认快捷键：
- F2: 开始/停止录音转录
- Shift + F2: 开始/停止录音翻译

## 构建本地包

如果需要从源码构建：

```bash
uv build
```

## 许可证

MIT