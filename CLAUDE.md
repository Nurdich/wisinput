# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Windows tray application for voice input that supports both cloud-based (Google Gemini) and local model transcription services. It provides keyboard shortcuts for recording and transcribing speech to text, with options for translation and floating window UI.

## High-Level Architecture

### Core Components
1. **Audio Recording** (`src/audio/recorder.py`) - Handles microphone input using `sounddevice` library
2. **Keyboard Management** (`src/keyboard/listener.py`) - Manages keyboard shortcuts and text input
3. **Floating Window UI** (`src/keyboard/floating_window.py`) - Optional Tkinter-based UI for status display
4. **Transcription Processors**:
   - Google AI (`src/transcription/google_ai.py`) - Cloud-based transcription using Google Gemini
   - Local Model (`src/transcription/local_model.py`) - Local HTTP service integration
5. **LLM Processing**:
   - Translation (`src/llm/translate.py`) - Text translation using Google Gemini
   - Text Optimization (`src/llm/symbol.py`) - Text punctuation and optimization using Google Gemini

### Entry Points
- `windows_app.py` - Main Windows tray application (recommended for production use)
- `main.py` - Terminal-based application with more features

## Development Commands

### Setup
```bash
pip install pip-tools
pip-compile requirements.in
pip install -r requirements.txt
```

### Configuration
1. Copy `.env.example` to `.env`
2. Configure `SERVICE_PLATFORM` (google|local)
3. Set API keys or local model settings

### Running the Application
```bash
# Windows tray mode (recommended)
python windows_app.py

# Terminal mode
python main.py

# Using uvx (recommended for easy installation and running)
# If package is published to PyPI
uvx whisper-input

# Or run directly from local source
uvx --from . whisper-input
```

### Local Model Setup
```bash
# Download models
python scripts/download_models.py

# Configure .env for local mode:
# SERVICE_PLATFORM=local
# LOCAL_MODEL_BASE_URL=http://localhost:8000
```

### Building Executable
```bash
pip install pyinstaller
pyinstaller -F -w windows_app.py --name WhisperInput
```

### Building and Installing with uv
```bash
# Build the package
uv build

# Install locally with pip
pip install .

# Run directly with uvx (if published)
uvx whisper-input

# Or run from local source
uvx --from . whisper-input
```

## Key Configuration Options

### Environment Variables (in .env)
- `SERVICE_PLATFORM` - google|local
- `GEMINI_API_KEY` - Google API key for cloud services
- `LOCAL_MODEL_BASE_URL` - URL for local model service
- `TRANSCRIPTIONS_BUTTON` - Keyboard shortcut for transcription
- `TRANSLATIONS_BUTTON` - Keyboard shortcut for translation
- `ENABLE_FLOATING_WINDOW` - Enable/disable floating window UI

## Code Patterns and Conventions

### Audio Processing Flow
1. Audio recording via `AudioRecorder`
2. Audio processing via `AudioProcessor` (Google or Local)
3. Text optimization via `SymbolProcessor`
4. Text input via `KeyboardManager`

### UI Patterns
- Floating window supports two modes: status (minimal) and full (interactive)
- Status updates via callback mechanisms
- Thread-safe UI updates using Tkinter's `after()` method

### Error Handling
- Timeouts implemented with threading decorators
- Graceful fallbacks for clipboard operations
- Comprehensive logging with file and console output

## Dependencies
- `sounddevice` - Audio recording
- `pynput` - Keyboard/mouse input
- `tkinter` - UI components
- `google-genai` - Google AI integration
- `httpx` - HTTP client for local model API
- `pystray` - System tray integration