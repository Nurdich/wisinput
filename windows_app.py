#!/usr/bin/env python3
"""
Windows 托盘应用（无控制台）


配置：
- ENABLE_FLOATING_WINDOW 建议改为 false，避免 Tk 主线程冲突；若要启用悬浮窗，请继续使用 main.py 入口
"""

import os
import sys
import threading

import pystray
from PIL import Image, ImageDraw

from src.utils.logger import logger
from src.transcription.google_ai import GoogleAiProcessor
from src.transcription.local_model import LocalModelProcessor
from src.keyboard.listener import KeyboardManager
from src.audio.recorder import AudioRecorder


def run_server():
    """在本机启动本地模型服务器（仅用于 SERVICE_PLATFORM=local）。
    优先使用环境变量 LOCAL_SERVER_SCRIPT 指定的脚本；否则回退到项目内的示例服务器。
    在 Windows 下隐藏控制台窗口，避免打扰用户。
    """
    
    import subprocess
    subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "speaches.main:create_app", "--host", "127.0.0.1", "--port", "8000", "--factory"],
        # creationflags=subprocess.CREATE_NEW_CONSOLE,
    )
    
    logger.info("本地服务已禁用，使用远程服务")

   


class TrayApp:
    def __init__(self):
        # 托盘版也支持悬浮窗。若未显式配置，默认开启并使用 status 模式
        os.environ.setdefault("ENABLE_FLOATING_WINDOW", "true")
        os.environ.setdefault("FLOATING_WINDOW_MODE", "status")

        # 选择 ASR 处理器（与 main.py 一致）
        service_platform = os.getenv("SERVICE_PLATFORM", "local").lower()
        if service_platform == "openai":
            self.audio_processor = GoogleAiProcessor()
        elif service_platform == "local":
            self.audio_processor = LocalModelProcessor()
        else:
            raise ValueError(f"无效的服务平台: {service_platform}")

        self.audio_recorder = AudioRecorder()
        # 若启用悬浮窗，为其提供电平回调
        try:
            self.audio_recorder.set_level_callback(lambda lv: self._set_level_safe(lv))
            # 推送实时样本用于波形绘制
            self.audio_recorder.set_samples_callback(lambda smp: self._push_wave_samples_safe(smp))
        except Exception:
            pass

        # 悬浮窗（可选）
        self.floating_window = None
        self.enable_floating_window = os.getenv("ENABLE_FLOATING_WINDOW", "true").lower() == "true"
        if self.enable_floating_window:
            try:
                from src.keyboard.floating_window import FloatingWindow
                self.floating_window = FloatingWindow(
                    on_record_start=self.start_transcription_recording,
                    on_record_stop=self.stop_transcription_recording,
                    on_translate_start=self.start_translation_recording,
                    on_translate_stop=self.stop_translation_recording,
                )
                logger.info("托盘版：悬浮窗已启用（status 模式）")
            except Exception as e:
                logger.error(f"初始化悬浮窗失败：{e}")
                self.enable_floating_window = False

        self.keyboard_manager = KeyboardManager(
            on_record_start=self.start_transcription_recording,
            on_record_stop=self.stop_transcription_recording,
            on_translate_start=self.start_translation_recording,
            on_translate_stop=self.stop_translation_recording,
            on_reset_state=self.reset_state,
            floating_window=self.floating_window,
        )

        self.icon = None
        self.server = None
        self.is_recording_transcription = False
        self.is_recording_translation = False

    # 录音回调（复制自 main.py）
    def start_transcription_recording(self):
        self.audio_recorder.start_recording()
        if self.floating_window:
            try:
                # 托盘触发时直接切换录音状态（status模式图标是常驻的）
                self.floating_window.reset_wave()
                if not self.floating_window.is_recording:
                    self.floating_window._toggle_recording()
            except Exception as e:
                logger.warning(f"托盘触发悬浮窗失败: {e}")
        self.is_recording_transcription = True

    def stop_transcription_recording(self):
        # 立即停止录音并更新UI状态
        self.is_recording_transcription = False
        if self.floating_window and self.floating_window.is_recording:
            try:
                self.floating_window._toggle_recording()
            except Exception as e:
                logger.warning(f"停止录音动画失败: {e}")
        
        # 获取录音数据
        audio = self.audio_recorder.stop_recording()
        
        # 确保文本输入框获得焦点
        if self.floating_window and hasattr(self.floating_window, 'text_widget'):
            try:
                self.floating_window.text_widget.focus_set()
            except Exception:
                pass

        if audio == "TOO_SHORT":
            logger.warning("录音时长太短，状态将重置")
            if self.floating_window:
                try:
                    self.floating_window.stop_processing()  # 停止处理状态
                    self.floating_window.set_text("⚠️ 录音时长过短")
                except Exception:
                    pass
            self.keyboard_manager.reset_state()
        elif audio:
            # 立即显示正在转录状态（不是处理状态）
            if self.floating_window:
                try:
                    self.floating_window.stop_processing()  # 先停止处理状态
                    self.floating_window.start_transcribing()  # 开始转录状态动画
                    self.floating_window.set_text("🔄 正在转录...")
                except Exception as e:
                    logger.warning(f"设置正在转录状态失败: {e}")
            
            # 在单独线程中进行转录，避免阻塞UI
            def transcribe_audio():
                try:
                    # 转录过程中保持显示状态
                    
                    result = self.audio_processor.process_audio(
                        audio,
                        mode="transcriptions",
                        prompt="",
                    )
                    text, error = result if isinstance(result, tuple) else (result, None)
                    
                    # 在主线程中更新UI
                    def update_ui():
                        try:
                            if self.floating_window:
                                self.floating_window.stop_transcribing()  # 停止转录状态动画
                                if error:
                                    self.floating_window.set_text(f"❌ {error}")
                                else:
                                    self.floating_window.set_text(text)
                            self.keyboard_manager.type_text(text, error)
                        except Exception as e:
                            logger.error(f"更新转录结果失败: {e}")
                    
                    if self.floating_window and self.floating_window.window:
                        self.floating_window.window.after(0, update_ui)
                    else:
                        self.keyboard_manager.type_text(text, error)
                        
                except Exception as e:
                    logger.error(f"转录过程出错: {e}")
                    def update_error():
                        try:
                            if self.floating_window:
                                self.floating_window.stop_transcribing()
                                self.floating_window.set_text(f"❌ 转录失败: {str(e)}")
                            self.keyboard_manager.type_text(None, f"转录失败: {str(e)}")
                        except Exception:
                            pass
                    
                    if self.floating_window and self.floating_window.window:
                        self.floating_window.window.after(0, update_error)
                    else:
                        self.keyboard_manager.type_text(None, f"转录失败: {str(e)}")
            
            # 启动转录线程
            threading.Thread(target=transcribe_audio, daemon=True).start()
        else:
            logger.error("没有录音数据，状态将重置")
            if self.floating_window:
                try:
                    self.floating_window.stop_processing()
                    self.floating_window.set_text("❌ 录音失败")
                    self.floating_window.reset_state()
                except Exception:
                    pass
            self.keyboard_manager.reset_state()

    def start_translation_recording(self):
        self.audio_recorder.start_recording()
        self.is_recording_translation = True
        if self.floating_window:
            try:
                # 托盘触发翻译录音（status模式图标是常驻的）
                self.floating_window.reset_wave()
                if not self.floating_window.is_recording:
                    self.floating_window._toggle_recording()
            except Exception:
                pass

    def _set_level_safe(self, lv: float):
        if self.floating_window and getattr(self.floating_window, 'window', None):
            try:
                self.floating_window.set_level(lv)
            except Exception:
                pass

    def _push_wave_samples_safe(self, samples):
        if self.floating_window and getattr(self.floating_window, 'window', None):
            try:
                self.floating_window.push_wave_samples(samples)
            except Exception:
                pass

    def stop_translation_recording(self):
        # 立即停止录音并更新UI状态
        self.is_recording_translation = False
        if self.floating_window and self.floating_window.is_recording:
            try:
                self.floating_window._toggle_recording()
            except Exception as e:
                logger.warning(f"停止录音动画失败: {e}")
        
        # 获取录音数据
        audio = self.audio_recorder.stop_recording()
        
        # 确保文本输入框获得焦点
        if self.floating_window and hasattr(self.floating_window, 'text_widget'):
            try:
                self.floating_window.text_widget.focus_set()
            except Exception:
                pass

        if audio == "TOO_SHORT":
            logger.warning("录音时长太短，状态将重置")
            if self.floating_window:
                try:
                    self.floating_window.stop_processing()  # 停止处理状态
                    self.floating_window.set_text("⚠️ 录音时长过短")
                except Exception:
                    pass
            self.keyboard_manager.reset_state()
        elif audio:
            # 立即显示正在翻译状态（不是处理状态）
            if self.floating_window:
                try:
                    self.floating_window.stop_processing()  # 先停止处理状态
                    self.floating_window.start_transcribing()  # 翻译也使用转录状态动画
                    self.floating_window.set_text("🔄 正在翻译...")
                except Exception as e:
                    logger.warning(f"设置正在翻译状态失败: {e}")
            
            # 在单独线程中进行翻译，避免阻塞UI
            def translate_audio():
                try:
                    # 翻译过程中保持显示状态
                    
                    result = self.audio_processor.process_audio(
                        audio,
                        mode="translations",
                        prompt="",
                    )
                    text, error = result if isinstance(result, tuple) else (result, None)
                    
                    # 在主线程中更新UI
                    def update_ui():
                        try:
                            if self.floating_window:
                                self.floating_window.stop_transcribing()  # 停止转录状态动画
                                if error:
                                    self.floating_window.set_text(f"❌ {error}")
                                else:
                                    self.floating_window.set_text(text)
                            self.keyboard_manager.type_text(text, error)
                        except Exception as e:
                            logger.error(f"更新翻译结果失败: {e}")
                    
                    if self.floating_window and self.floating_window.window:
                        self.floating_window.window.after(0, update_ui)
                    else:
                        self.keyboard_manager.type_text(text, error)
                        
                except Exception as e:
                    logger.error(f"翻译过程出错: {e}")
                    def update_error():
                        try:
                            if self.floating_window:
                                self.floating_window.stop_transcribing()
                                self.floating_window.set_text(f"❌ 翻译失败: {str(e)}")
                            self.keyboard_manager.type_text(None, f"翻译失败: {str(e)}")
                        except Exception:
                            pass
                    
                    if self.floating_window and self.floating_window.window:
                        self.floating_window.window.after(0, update_error)
                    else:
                        self.keyboard_manager.type_text(None, f"翻译失败: {str(e)}")
            
            # 启动翻译线程
            threading.Thread(target=translate_audio, daemon=True).start()
        else:
            logger.error("没有录音数据，状态将重置")
            if self.floating_window:
                try:
                    self.floating_window.stop_processing()
                    self.floating_window.set_text("❌ 录音失败")
                    self.floating_window.reset_state()
                except Exception:
                    pass
            self.keyboard_manager.reset_state()

    def reset_state(self):
        self.keyboard_manager.reset_state()

    def _create_icon_image(self):
        # 创建一个简单的 16x16 图标
        img = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.ellipse((1, 1, 15, 15), fill=(52, 152, 219, 255))
        d.rectangle((7, 4, 9, 12), fill=(255, 255, 255, 255))  # 麦克风杆
        d.ellipse((5, 3, 11, 7), fill=(255, 255, 255, 255))   # 麦克风头
        return img

    # -------- 托盘菜单动作 --------
    def _action_toggle_transcription(self, icon, item):
        try:
            if not self.is_recording_transcription and not self.is_recording_translation:
                self.start_transcription_recording()
            elif self.is_recording_transcription:
                self.stop_transcription_recording()
        finally:
            self._refresh_menu()

    def _action_toggle_translation(self, icon, item):
        try:
            if not self.is_recording_translation and not self.is_recording_transcription:
                self.start_translation_recording()
            elif self.is_recording_translation:
                self.stop_translation_recording()
        finally:
            self._refresh_menu()

    def _action_toggle_click_mode(self, icon, item):
        # 切换 键盘单击/长按 模式
        self.keyboard_manager.toggle_mode = not getattr(self.keyboard_manager, 'toggle_mode', True)
        state_text = "单击切换" if self.keyboard_manager.toggle_mode else "长按触发"
        logger.info(f"快捷键模式已切换为：{state_text}")
        self._refresh_menu()

    def _action_open_logs(self, icon, item):
        logs_dir = os.path.join(os.getcwd(), "logs")
        try:
            os.makedirs(logs_dir, exist_ok=True)
            os.startfile(logs_dir)
        except Exception as e:
            logger.error(f"打开日志目录失败：{e}")

    def _action_restart_local_server(self, icon, item):
        try:
            # uvicorn.Server 没有优雅的 stop；简单起见不重启已运行的，提示用户重启应用
            logger.info("如需更换本地服务配置，请重启托盘应用。")
        except Exception:
            pass

    def _build_menu(self):
        # 动态标题
        t_label = "停止录音（转写）" if self.is_recording_transcription else "开始录音（转写）"
        tr_label = "停止录音（翻译）" if self.is_recording_translation else "开始录音（翻译）"
        click_mode_label = "模式：单击切换" if getattr(self.keyboard_manager, 'toggle_mode', True) else "模式：长按触发"

        return pystray.Menu(
            pystray.MenuItem(t_label, self._action_toggle_transcription, default=True),
            pystray.MenuItem(tr_label, self._action_toggle_translation),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(click_mode_label, self._action_toggle_click_mode),
            pystray.MenuItem("打开日志目录", self._action_open_logs),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("退出 Exit", self._on_exit),
        )

    def _refresh_menu(self):
        if self.icon is not None:
            self.icon.menu = self._build_menu()
            try:
                self.icon.update_menu()
            except Exception:
                pass

    def _on_exit(self, icon, item):
        try:
            # 无显式停止 pynput 监听 API，这里让进程退出
            pass
        finally:
            icon.stop()
            os._exit(0)

    def _run_tray(self):
        # 托盘（阻塞式）
        self.icon = pystray.Icon("WhisperInput", self._create_icon_image(), "Whisper Input", self._build_menu())
        logger.info("托盘已启动，程序在后台运行。")
        self.icon.run()

    def run(self):
        # 仅在本地模式下启动本地服务
        try:
            service_platform = os.getenv("SERVICE_PLATFORM", "local").lower()
            if service_platform == "local":
                threading.Thread(target=run_server, daemon=True).start()
                logger.info("本地服务启动请求已发出（local 模式）")
        except Exception:
            pass
        # 后台启动键盘监听
        threading.Thread(target=self.keyboard_manager.start_listening, daemon=True).start()

        if self.enable_floating_window and self.floating_window is not None:
            # 托盘放后台线程，主线程运行 Tk（避免 Tcl 线程错误）
            threading.Thread(target=self._run_tray, daemon=True).start()
            self.floating_window.run()
        else:
            # 无浮窗：托盘占用主线程
            self._run_tray()


def main():
    try:
        TrayApp().run()
    except Exception as e:
        logger.error(f"程序启动失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()


