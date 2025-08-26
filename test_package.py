#!/usr/bin/env python3
"""
Simple test script to verify that the whisper-input package can be imported and run.
"""

import sys
import os

def test_imports():
    """Test that all required modules can be imported."""
    try:
        # Test core modules
        from windows_app import main
        from src.audio.recorder import AudioRecorder
        from src.keyboard.listener import KeyboardManager
        from src.transcription.google_ai import GoogleAiProcessor
        from src.transcription.local_model import LocalModelProcessor
        from src.llm.translate import TranslateProcessor
        from src.llm.symbol import SymbolProcessor
        from src.utils.logger import logger
        
        print("✓ All modules imported successfully")
        return True
    except Exception as e:
        print(f"✗ Import failed: {e}")
        return False

def test_environment():
    """Test that required environment variables are set."""
    required_vars = ['SERVICE_PLATFORM']
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        print(f"⚠ Warning: Missing environment variables: {missing_vars}")
        print("  Please ensure .env file is properly configured")
        return False
    else:
        print("✓ Required environment variables are set")
        return True

def main():
    print("Testing whisper-input package...")
    print("=" * 40)
    
    success = True
    success &= test_imports()
    success &= test_environment()
    
    print("=" * 40)
    if success:
        print("✓ All tests passed! The package is ready to use.")
        return 0
    else:
        print("✗ Some tests failed. Please check the errors above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())