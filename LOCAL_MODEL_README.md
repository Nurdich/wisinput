# 本地模型支持

本项目现在支持使用本地部署的语音转录模型，为用户提供更多的隐私保护和自定义选项。

## 功能特性

- 🔒 **隐私保护**: 音频数据不会发送到外部服务器
- ⚡ **低延迟**: 本地处理，无网络延迟
- 🛠️ **可定制**: 可以使用任何兼容的本地模型
- 🔄 **统一接口**: 与现有的 Whisper 和 SenseVoice 处理器保持一致的接口
- ✏️ **智能标点**: 支持自动添加标点符号和优化识别结果
- 🌐 **翻译支持**: 支持将识别结果翻译为英文

## 快速开始

### 1. 配置环境变量

在 `.env` 文件中添加以下配置：

```bash
# 设置服务平台为本地模型
SERVICE_PLATFORM=local

# 本地模型服务器地址（默认: http://localhost:8000）
LOCAL_MODEL_BASE_URL=http://localhost:8000

# 本地模型名称（默认: Systran/faster-whisper-large-v3）
LOCAL_MODEL_NAME=Systran/faster-whisper-large-v3

# 请求超时时间（秒，默认: 20）
LOCAL_MODEL_TIMEOUT=20

# 认证令牌（可选，如果本地服务需要认证）
LOCAL_MODEL_AUTH_TOKEN=your_token_here

# 标点符号和优化功能（需要 GROQ API）
ADD_SYMBOL=true
OPTIMIZE_RESULT=false
GROQ_API_KEY=your_groq_api_key_here
GROQ_BASE_URL=https://api.groq.com/openai/v1
GROQ_ADD_SYMBOL_MODEL=llama-3.3-70b-versatile
```

### 2. 启动本地模型服务

#### 选项 A: 使用提供的示例服务器（仅用于测试）

```bash
# 安装依赖
pip install fastapi uvicorn python-multipart

# 启动示例服务器
python local_server_example.py
```

#### 选项 B: 使用真实的语音识别服务

你可以使用任何提供兼容API的本地语音识别服务，例如：

- **Whisper API 服务器**: 使用 OpenAI Whisper 的本地部署
- **自定义模型**: 基于 Hugging Face Transformers 的自定义服务
- **其他开源方案**: 如 Vosk、SpeechRecognition 等

### 3. 运行语音助手

```bash
python main.py
```

## API 接口规范

本地模型服务器需要提供以下API端点：

### POST /v1/audio/transcriptions

**请求格式:**
- Method: POST
- Content-Type: multipart/form-data
- Body:
  - `file`: 音频文件 (WAV格式)
  - `model`: 模型名称 (例如: "Systran/faster-whisper-large-v3")

**响应格式:**
```json
{
  "text": "转录结果文本"
}
```

**可选的响应格式:**
```json
{
  "transcription": "转录结果文本"
}
```

或者：
```json
{
  "result": "转录结果文本"
}
```

### GET /health (可选)

健康检查端点，用于测试服务器连接。

## 标点符号和优化功能

本地模型支持与其他处理器相同的标点符号添加和结果优化功能。

### 配置说明

标点符号和优化功能使用 OpenAI 兼容的 API（推荐使用 GROQ）：

```bash
# 启用标点符号功能
ADD_SYMBOL=true

# 启用结果优化功能（实验性）
OPTIMIZE_RESULT=false

# GROQ API 配置（用于标点符号功能）
GROQ_API_KEY=your_groq_api_key_here
GROQ_BASE_URL=https://api.groq.com/openai/v1
GROQ_ADD_SYMBOL_MODEL=llama-3.3-70b-versatile
```

### 功能说明

1. **标点符号添加** (`ADD_SYMBOL=true`)
   - 自动为转录结果添加合适的标点符号
   - 提高文本的可读性
   - 不改变原文内容，只添加标点

2. **结果优化** (`OPTIMIZE_RESULT=true`)
   - 修正语音识别中的明显错误
   - 优化语法和表达
   - 实验性功能，可能影响准确性

### 注意事项

- 标点符号功能需要额外的 API 调用，会增加处理时间
- 如果没有配置 GROQ API Key，这些功能将被跳过
- 可以单独启用或禁用每个功能

## 测试工具

### 连接测试

使用提供的测试脚本验证本地模型配置：

```bash
python test_local_model.py
```

### 功能测试

1. 确保本地服务器正在运行
2. 将测试音频文件命名为 `test_audio.wav` 并放在项目根目录
3. 运行测试脚本

## 集成真实模型

### 使用 Whisper 本地服务

```python
# 示例：使用 OpenAI Whisper 创建本地服务
import whisper
from fastapi import FastAPI, File, UploadFile
import tempfile
import os

app = FastAPI()
model = whisper.load_model("base")

@app.post("/v1/audio/transcriptions")
async def transcribe(file: UploadFile = File(...)):
    # 保存临时文件
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp_file:
        content = await file.read()
        tmp_file.write(content)
        tmp_file_path = tmp_file.name
    
    try:
        # 使用 Whisper 进行转录
        result = model.transcribe(tmp_file_path)
        return {"text": result["text"]}
    finally:
        # 清理临时文件
        os.unlink(tmp_file_path)
```

### 使用 Hugging Face Transformers

```python
from transformers import pipeline
from fastapi import FastAPI, File, UploadFile
import tempfile
import os

app = FastAPI()
transcriber = pipeline("automatic-speech-recognition", model="openai/whisper-base")

@app.post("/v1/audio/transcriptions")
async def transcribe(file: UploadFile = File(...)):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp_file:
        content = await file.read()
        tmp_file.write(content)
        tmp_file_path = tmp_file.name
    
    try:
        result = transcriber(tmp_file_path)
        return {"text": result["text"]}
    finally:
        os.unlink(tmp_file_path)
```

## 故障排除

### 常见问题

1. **连接失败**
   - 检查本地服务器是否正在运行
   - 验证 `LOCAL_MODEL_BASE_URL` 配置是否正确
   - 确保防火墙没有阻止连接

2. **转录失败**
   - 检查音频文件格式是否支持
   - 查看服务器日志获取详细错误信息
   - 验证音频文件是否损坏

3. **超时错误**
   - 增加 `LOCAL_MODEL_TIMEOUT` 值
   - 检查模型处理速度
   - 考虑使用更快的模型

### 日志调试

启用详细日志以获取更多调试信息：

```bash
# 在 .env 文件中设置日志级别
LOG_LEVEL=DEBUG
```

## 性能优化

1. **模型选择**: 根据需求选择合适大小的模型
2. **硬件加速**: 使用 GPU 加速推理
3. **批处理**: 如果支持，可以实现批量处理
4. **缓存**: 对重复音频实现结果缓存

## 安全考虑

1. **网络安全**: 如果在网络环境中部署，确保使用 HTTPS
2. **访问控制**: 实现适当的认证和授权机制
3. **数据保护**: 确保音频数据的安全处理和存储

## 贡献

欢迎提交 Issue 和 Pull Request 来改进本地模型支持功能！
