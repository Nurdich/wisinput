import os
import sys

from dotenv import load_dotenv

load_dotenv()

from src.audio.recorder import AudioRecorder
from src.keyboard.listener import KeyboardManager, check_accessibility_permissions
from src.transcription.google_ai import GoogleAiProcessor
from src.utils.logger import logger
from src.transcription.local_model import LocalModelProcessor
from src.llm.symbol import SymbolProcessor


def check_microphone_permissions():
    """检查麦克风权限并提供指导"""
    logger.warning("\n=== macOS 麦克风权限检查 ===")
    logger.warning("此应用需要麦克风权限才能进行录音。")
    logger.warning("\n请按照以下步骤授予权限：")
    logger.warning("1. 打开 系统偏好设置")
    logger.warning("2. 点击 隐私与安全性")
    logger.warning("3. 点击左侧的 麦克风")
    logger.warning("4. 点击右下角的锁图标并输入密码")
    logger.warning("5. 在右侧列表中找到 Terminal（或者您使用的终端应用）并勾选")
    logger.warning("\n授权后，请重新运行此程序。")
    logger.warning("===============================\n")

class VoiceAssistant:
    def __init__(self, audio_processor):
        self.audio_recorder = AudioRecorder()
        self.audio_processor = audio_processor
        
        # 悬浮窗支持
        self.floating_window = None
        self.enable_floating_window = os.getenv("ENABLE_FLOATING_WINDOW", "true").lower() == "true"
        
        if self.enable_floating_window:
            try:
                from src.keyboard.floating_window import FloatingWindow
                # 初始化优化器（统一使用 Google/Gemini）
                self.symbol_processor = SymbolProcessor(service_platform=os.getenv("SERVICE_PLATFORM", "google"))
                # 创建悬浮窗（状态模式默认），注册回调
                self.floating_window = FloatingWindow(
                    on_record_start=self.start_transcription_recording,
                    on_record_stop=self.stop_transcription_recording,
                    on_translate_start=self.start_translation_recording,
                    on_translate_stop=self.stop_translation_recording
                )
                logger.info("悬浮窗功能已启用")
                # 串联实时电平与样本回调（用于波形与电平显示）
                try:
                    self.audio_recorder.set_level_callback(lambda lv: self._set_level_safe(lv))
                    self.audio_recorder.set_samples_callback(lambda smp: self._push_wave_samples_safe(smp))
                except Exception:
                    pass
            except ImportError as e:
                logger.error(f"悬浮窗模块导入失败: {e}")
                self.enable_floating_window = False
            except Exception as e:
                logger.error(f"悬浮窗初始化失败: {e}")
                self.enable_floating_window = False
        
        # 创建键盘管理器，传递悬浮窗引用
        self.keyboard_manager = KeyboardManager(
            on_record_start=self.start_transcription_recording,
            on_record_stop=self.stop_transcription_recording,
            on_translate_start=self.start_translation_recording,
            on_translate_stop=self.stop_translation_recording,
            on_reset_state=self.reset_state,
            floating_window=self.floating_window
        )
    
    def start_transcription_recording(self):
        """开始录音（转录模式）"""
        self.audio_recorder.start_recording()
        if self.floating_window:
            try:
                self.floating_window.window.after(0, lambda: (
                    self.floating_window.reset_wave(),
                    self.floating_window._show_at_position(self.floating_window.mouse_x, self.floating_window.mouse_y),
                    self.floating_window.update_status("🎤 正在录音...")
                ))
            except Exception:
                pass
    
    def stop_transcription_recording(self):
        """停止录音并处理（转录模式）"""
        audio = self.audio_recorder.stop_recording()
        if audio == "TOO_SHORT":
            logger.warning("录音时长太短，状态将重置")
            if self.floating_window:
                try:
                    self.floating_window.window.after(0, lambda: (
                        self.floating_window.update_status("⚠️ 录音时长过短"),
                        self.floating_window.reset_state()
                    ))
                except Exception:
                    pass
            self.keyboard_manager.reset_state()
        elif audio:
            if self.floating_window:
                try:
                    self.floating_window.window.after(0, lambda: self.floating_window.update_status("🔄 正在转录..."))
                except Exception:
                    pass
            result = self.audio_processor.process_audio(
                audio,
                mode="transcriptions",
                prompt=""
            )
            # 解构返回值
            text, error = result if isinstance(result, tuple) else (result, None)
            if self.floating_window:
                try:
                    if error:
                        self.floating_window.window.after(0, lambda: self.floating_window.update_status(f"❌ {error}"))
                    else:
                        self.floating_window.window.after(0, lambda: self.floating_window.update_status("✅ 转录完成"))
                except Exception:
                    pass
            self.keyboard_manager.type_text(text, error)
        else:
            logger.error("没有录音数据，状态将重置")
            if self.floating_window:
                try:
                    self.floating_window.window.after(0, lambda: (
                        self.floating_window.update_status("❌ 录音失败"),
                        self.floating_window.reset_state()
                    ))
                except Exception:
                    pass
            self.keyboard_manager.reset_state()
    
    def start_translation_recording(self):
        """开始录音（翻译模式）"""
        self.audio_recorder.start_recording()
        if self.floating_window:
            try:
                self.floating_window.window.after(0, lambda: (
                    self.floating_window.reset_wave(),
                    self.floating_window._show_at_position(self.floating_window.mouse_x, self.floating_window.mouse_y),
                    self.floating_window.update_status("🎤 正在录音 (翻译模式)")
                ))
            except Exception:
                pass

    # 与悬浮窗主线程交互的安全封装
    def _set_level_safe(self, lv: float):
        if self.floating_window and getattr(self.floating_window, 'window', None):
            try:
                self.floating_window.window.after(0, lambda: self.floating_window.set_level(lv))
            except Exception:
                pass

    def _push_wave_samples_safe(self, samples):
        if self.floating_window and getattr(self.floating_window, 'window', None):
            try:
                self.floating_window.window.after(0, lambda s=samples: self.floating_window.push_wave_samples(s))
            except Exception:
                pass
    
    def stop_translation_recording(self):
        """停止录音并处理（翻译模式）"""
        audio = self.audio_recorder.stop_recording()
        if audio == "TOO_SHORT":
            logger.warning("录音时长太短，状态将重置")
            if self.floating_window:
                try:
                    self.floating_window.window.after(0, lambda: (
                        self.floating_window.update_status("⚠️ 录音时长过短"),
                        self.floating_window.reset_state()
                    ))
                except Exception:
                    pass
            self.keyboard_manager.reset_state()
        elif audio:
            if self.floating_window:
                try:
                    self.floating_window.window.after(0, lambda: self.floating_window.update_status("🔄 正在翻译..."))
                except Exception:
                    pass
            result = self.audio_processor.process_audio(
                    audio,
                    mode="translations",
                    prompt=""
                )
            text, error = result if isinstance(result, tuple) else (result, None)
            if self.floating_window:
                try:
                    if error:
                        self.floating_window.window.after(0, lambda: self.floating_window.update_status(f"❌ {error}"))
                    else:
                        self.floating_window.window.after(0, lambda: self.floating_window.update_status("✅ 翻译完成"))
                except Exception:
                    pass
            self.keyboard_manager.type_text(text,error)
        else:
            logger.error("没有录音数据，状态将重置")
            if self.floating_window:
                try:
                    self.floating_window.window.after(0, lambda: (
                        self.floating_window.update_status("❌ 录音失败"),
                        self.floating_window.reset_state()
                    ))
                except Exception:
                    pass
            self.keyboard_manager.reset_state()

    def reset_state(self):
        """重置状态"""
        self.keyboard_manager.reset_state()
        if self.floating_window:
            try:
                self.floating_window.window.after(0, self.floating_window.reset_state)
            except Exception:
                pass
    
    def run(self):
        """运行语音助手"""
        logger.info("=== 语音助手已启动 ===")
        
        if self.enable_floating_window:
            logger.info("悬浮窗模式：按下快捷键或右键点击显示悬浮窗")
            logger.info("悬浮窗功能：点击录音按钮开始/停止录音，点击翻译按钮开始/停止翻译录音")
            logger.info("悬浮窗位置：出现在鼠标当前位置，不会跟随鼠标移动")

            # 后台启动键盘监听；Tk 必须在主线程运行
            import threading
            keyboard_thread = threading.Thread(target=self.keyboard_manager.start_listening, daemon=True)
            keyboard_thread.start()

            # 在主线程运行 Tk mainloop
            self.floating_window.run()
        else:
            logger.info("键盘模式：使用配置的快捷键进行语音输入")
            self.keyboard_manager.start_listening()

    # ============ 写入目标窗口 ============
    def _write_text_to_target(self, text: str, hwnd):
        """将文本写入目标窗口（Windows 优先使用窗口句柄）。其他平台回退到直接键入/粘贴。"""
        try:
            if os.getenv("SYSTEM_PLATFORM") == "win" and hwnd:
                import ctypes
                from ctypes import wintypes
                user32 = ctypes.WinDLL('user32', use_last_error=True)
                # 将目标窗口置前并设置焦点（同时附加到同输入队列以提高成功率）
                try:
                    foreground = user32.GetForegroundWindow()
                    thread_fore = user32.GetWindowThreadProcessId(foreground, None)
                    thread_target = user32.GetWindowThreadProcessId(hwnd, None)
                    user32.AttachThreadInput(thread_fore, thread_target, True)
                except Exception:
                    pass
                user32.ShowWindow(hwnd, 9)  # SW_RESTORE
                user32.SetForegroundWindow(hwnd)
                # 小延时等待焦点稳定
                import time as _time
                _time.sleep(0.05)
                try:
                    # 解绑线程输入
                    foreground = user32.GetForegroundWindow()
                    thread_fore = user32.GetWindowThreadProcessId(foreground, None)
                    thread_target = user32.GetWindowThreadProcessId(hwnd, None)
                    user32.AttachThreadInput(thread_fore, thread_target, False)
                except Exception:
                    pass
            # 优先使用 WM_CHAR 写入，避免部分场景 SendInput 返回 87
            if os.getenv("SYSTEM_PLATFORM") == "win" and hwnd:
                try:
                    import ctypes
                    from ctypes import wintypes
                    user32 = ctypes.WinDLL('user32', use_last_error=True)
                    WM_CHAR = 0x0102

                    # 定义 WPARAM/LPARAM/LRESULT（不同 Python 版本下 wintypes 可能缺失）
                    if ctypes.sizeof(ctypes.c_void_p) == 8:
                        WPARAM = ctypes.c_ulonglong
                        LPARAM = ctypes.c_longlong
                        LRESULT = ctypes.c_longlong
                    else:
                        WPARAM = ctypes.c_uint
                        LPARAM = ctypes.c_long
                        LRESULT = ctypes.c_long

                    user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, WPARAM, LPARAM]
                    user32.SendMessageW.restype = LRESULT

                    data = text.replace('\r\n', '\n').replace('\r', '\n')
                    encoded = data.encode('utf-16-le')
                    for i in range(0, len(encoded), 2):
                        code_unit = int.from_bytes(encoded[i:i+2], 'little')
                        if code_unit == 0x000A:
                            # 映射为回车
                            code_unit = 0x000D
                        user32.SendMessageW(hwnd, WM_CHAR, WPARAM(code_unit), LPARAM(0))
                    return
                except Exception as e_wm:
                    logger.warning(f"WM_CHAR 写入失败，将回退到剪贴板粘贴：{e_wm}")
                    # 回退到剪贴板粘贴以提升成功率（使用备份恢复机制）
                    if self.keyboard_manager._clipboard_paste_with_backup(text):
                        return
                    else:
                        logger.warning("剪贴板粘贴失败，最后回退到键盘注入")
            # 最后回退：使用键盘管理器的直接输入能力（支持中文/Unicode）
            self.keyboard_manager._type_text_direct(text)
        except Exception as e:
            logger.error(f"写入目标窗口失败：{e}")
            # 退回到剪贴板粘贴（使用备份恢复机制）
            if not self.keyboard_manager._clipboard_paste_with_backup(text):
                logger.error("所有输入方法都失败了")

def main():
    # 判断使用哪个音频处理器
    service_platform = os.getenv("SERVICE_PLATFORM", "google")
    if service_platform == "google":
        audio_processor = GoogleAiProcessor()
    elif service_platform == "local":
        audio_processor = LocalModelProcessor()
        # 测试本地服务器连接
        if not audio_processor.test_connection():
            logger.error("无法连接到本地模型服务器，请确保服务正在运行")
            sys.exit(1)
        logger.info("本地模型服务器连接成功")
    else:
        raise ValueError(f"无效的服务平台: {service_platform}，支持的平台: google, local")
    try:
        assistant = VoiceAssistant(audio_processor)
        assistant.run()
    except Exception as e:
        error_msg = str(e)
        if "Input event monitoring will not be possible" in error_msg:
            check_accessibility_permissions()
            sys.exit(1)
        elif "无法访问音频设备" in error_msg:
            check_microphone_permissions()
            sys.exit(1)
        else:
            logger.error(f"发生错误: {error_msg}", exc_info=True)
            sys.exit(1)

if __name__ == "__main__":
    main() 