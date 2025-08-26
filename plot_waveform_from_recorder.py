#!/usr/bin/env python3
"""
使用项目内的 AudioRecorder 录制 N 秒音频，并用 matplotlib 绘制波形。
依赖：matplotlib、soundfile（项目已用），无需 PyAudio。

运行：
  python examples/plot_waveform_from_recorder.py
或在不显示控制台情况下（Windows）：
  pythonw.exe examples/plot_waveform_from_recorder.py
"""

import time
import numpy as np
import soundfile as sf
import matplotlib.pyplot as plt

from src.audio.recorder import AudioRecorder

RECORD_SECONDS = 5  # 录音秒数


def main():
    print("* 录音中...")
    recorder = AudioRecorder()
    recorder.start_recording()
    time.sleep(RECORD_SECONDS)
    audio_buffer = recorder.stop_recording()

    if audio_buffer is None:
        print("* 未获取到音频数据")
        return
    if audio_buffer == "TOO_SHORT":
        print("* 录音过短，请增加 RECORD_SECONDS")
        return

    # 读取 BytesIO 中的 WAV，得到 numpy 数组和采样率
    data, samplerate = sf.read(audio_buffer, dtype="float32")

    # 展平为单声道（若为多声道）
    if data.ndim > 1:
        data = data[:, 0]

    # 生成时间轴
    duration = len(data) / float(samplerate)
    t = np.linspace(0, duration, num=len(data), endpoint=False)

    # 绘图
    plt.figure(figsize=(12, 4))
    plt.plot(t, data, linewidth=0.8)
    plt.title("音频波形图")
    plt.xlabel("时间 (s)")
    plt.ylabel("幅度")
    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    main()


