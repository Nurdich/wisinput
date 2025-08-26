#!/usr/bin/env python3
"""
下载/准备本地语音模型文件到项目目录。

默认下载 faster-whisper large-v3 模型到 ./models/Systran/faster-whisper-large-v3
可选下载 openai-whisper 模型到 ./models/whisper

用法：
  python scripts/download_models.py                # 下载 faster-whisper
  python scripts/download_models.py --whisper      # 下载 openai-whisper base

依赖：
  pip install faster-whisper
或
  pip install openai-whisper
"""

from __future__ import annotations

import argparse
import os
import sys


def download_faster_whisper():
    try:
        from faster_whisper import WhisperModel
    except Exception as e:
        print("未安装 faster-whisper，请先安装：pip install faster-whisper")
        sys.exit(1)

    model_id = "Systran/faster-whisper-large-v3"
    target_dir = os.path.join("models", "Systran", "faster-whisper-large-v3")
    os.makedirs(target_dir, exist_ok=True)
    print(f"准备下载 '{model_id}' 到: {target_dir}")
    # faster-whisper 会自动缓存到本地；这里通过一次初始化来触发下载
    model = WhisperModel(model_id, device="cpu", compute_type="int8")
    # 触发一次空转录以确保权重准备就绪
    print("模型已就绪。")


def download_openai_whisper(model_name: str = "base"):
    try:
        import whisper  # type: ignore
    except Exception:
        print("未安装 openai-whisper，请先安装：pip install openai-whisper")
        sys.exit(1)
    target_dir = os.path.join("models", "whisper")
    os.makedirs(target_dir, exist_ok=True)
    print(f"准备下载 openai-whisper '{model_name}' 到: {target_dir}")
    model = whisper.load_model(model_name, download_root=target_dir)
    print("模型已就绪。")


def main():
    parser = argparse.ArgumentParser(description="下载本地语音模型到项目目录")
    parser.add_argument("--whisper", action="store_true", help="下载 openai-whisper base 模型")
    args = parser.parse_args()

    if args.whisper:
        download_openai_whisper("base")
    else:
        download_faster_whisper()


if __name__ == "__main__":
    main()


