from pynput.keyboard import Controller, Key, Listener
import pyperclip
from ..utils.logger import logger
import time
from .inputState import InputState
import os
import sys
import ctypes
from ctypes import wintypes
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
from ctypes import cast, POINTER
from comtypes import CLSCTX_ALL


class KeyboardManager:
    def __init__(self, on_record_start, on_record_stop, on_translate_start, on_translate_stop, on_reset_state, floating_window=None):
        self.keyboard = Controller()
        self.pressed_keys = set()
        self.temp_text_length = 0  # 用于跟踪临时文本的长度
        self.processing_text = None  # 用于跟踪正在处理的文本
        self.error_message = None  # 用于跟踪错误信息
        self.warning_message = None  # 用于跟踪警告信息
        self._original_clipboard = None  # 保存原始剪贴板内容
        self.original_audio_states = {} # 保存原始音量和静音状态
        # 输入模式：'type' 直接键入（不占用剪贴板），'paste' 使用剪贴板粘贴
        self.input_mode = os.getenv("INPUT_MODE", "type").lower()
        # 悬浮窗引用
        self.floating_window = floating_window
        # V2 版本强制使用“按住模式”
        self.toggle_mode = False
        self.is_recording = False
        # 防抖：按住同一按键仅算一次
        self._trans_key_down = False
        self._transl_key_down = False
        
        
        # 回调函数
        self.on_record_start = on_record_start
        self.on_record_stop = on_record_stop
        self.on_translate_start = on_translate_start
        self.on_translate_stop = on_translate_stop
        self.on_reset_state = on_reset_state

        
        # 状态管理
        self._state = InputState.IDLE
        self._state_messages = {
            InputState.IDLE: "",
            InputState.RECORDING: "🎤 正在录音...",
            InputState.RECORDING_TRANSLATE: "🎤 正在录音 (翻译模式)",
            InputState.PROCESSING: "🔄 正在转录...",
            InputState.TRANSLATING: "🔄 正在翻译...",
            InputState.ERROR: lambda msg: f"{msg}",  # 错误消息使用函数动态生成
            InputState.WARNING: lambda msg: f"⚠️ {msg}"  # 警告消息使用函数动态生成
        }

        # 获取系统平台
        sysetem_platform = os.getenv("SYSTEM_PLATFORM")
        if sysetem_platform == "win" :
            self.sysetem_platform = Key.ctrl
            logger.info("配置到Windows平台")
        else:
            self.sysetem_platform = Key.cmd
            logger.info("配置到Mac平台")
        

        # 获取转录和翻译按钮
        transcriptions_button = os.getenv("TRANSCRIPTIONS_BUTTON", "alt_l")
        self.transcriptions_button = self.parse_hotkey(transcriptions_button)
        if not self.transcriptions_button:
            logger.error(f"无效的转录按钮配置：{transcriptions_button}")
        else:
            logger.info(f"配置到转录按钮：{transcriptions_button}")
            if sysetem_platform == "win" and any(key in [Key.alt, Key.alt_l, Key.alt_r] for key in self.transcriptions_button):
                logger.warning("⚠️ Windows中使用ALT键可能被系统拦截，建议使用F1-F12功能键")
                logger.warning("如果ALT键不工作，请尝试：TRANSCRIPTIONS_BUTTON=f8")

        translations_button = os.getenv("TRANSLATIONS_BUTTON", "f7")
        self.translations_button = self.parse_hotkey(translations_button)
        if not self.translations_button:
            logger.error(f"无效的翻译按钮配置：{translations_button}")
        else:
            logger.info(f"配置到翻译按钮(与转录按钮组合)：{translations_button}")
            if sysetem_platform == "win" and any(key in [Key.alt, Key.alt_l, Key.alt_r] for key in self.translations_button):
                logger.warning("⚠️ Windows中使用ALT键可能被系统拦截，建议使用F1-F12功能键")
                logger.warning("如果ALT键不工作，请尝试：TRANSLATIONS_BUTTON=f7")

        logger.info(f"按住 {transcriptions_button} 键：实时语音转录（保持原文）")
        logger.info(f"按住 {translations_button} + {transcriptions_button} 键：实时语音翻译（翻译成英文）")
        logger.info(f"输入模式：{self.input_mode}  (type=直接键入, paste=剪贴板粘贴)")
    
    @property
    def state(self):
        """获取当前状态"""
        return self._state

    def parse_hotkey(self, hotkey_str):
        """解析热键字符串，返回pynput键的集合。"""
        if not hotkey_str:
            return set()
        keys = set()
        for key_name in hotkey_str.split('+'):
            key_name = key_name.strip()
            try:
                # 首先尝试从Key枚举中获取
                keys.add(Key[key_name])
            except KeyError:
                # 如果失败，则假定为常规字符键
                if len(key_name) == 1:
                    keys.add(key_name)
                else:
                    logger.error(f"无效的键名：{key_name}")
                    return set()
        return keys

    @state.setter
    def state(self, new_state):
        """设置新状态并更新UI"""
        if new_state != self._state:
            self._state = new_state
            
            # 获取状态消息
            message = self._state_messages[new_state]
            
            # 根据状态转换类型显示不同消息
            match new_state:
                case InputState.RECORDING :
                    # 录音状态
                    self.temp_text_length = 0
                    self.type_temp_text(message)
                    self.on_record_start()
                    
                
                case InputState.RECORDING_TRANSLATE:
                    # 翻译,录音状态
                    self.temp_text_length = 0
                    self.type_temp_text(message)
                    self.on_translate_start()

                case InputState.PROCESSING:
                    self._delete_previous_text()
                    self.type_temp_text(message)
                    self.processing_text = message
                    self.on_record_stop()
                    # 进入处理后，暂时隐藏悬浮窗，避免遮挡（status模式除外）
                    if self.floating_window and getattr(self.floating_window, 'mode', 'full') != 'status':
                        try:
                            self.floating_window.window.after(0, self.floating_window.hide)
                        except Exception:
                            pass

                case InputState.TRANSLATING:
                    # 翻译状态
                    self._delete_previous_text()                 
                    self.type_temp_text(message)
                    self.processing_text = message
                    self.on_translate_stop()
                    # 翻译处理时隐藏悬浮窗（status模式除外）
                    if self.floating_window and getattr(self.floating_window, 'mode', 'full') != 'status':
                        try:
                            self.floating_window.window.after(0, self.floating_window.hide)
                        except Exception:
                            pass
                
                case InputState.WARNING:
                    # 警告状态
                    message = message(self.warning_message)
                    self._delete_previous_text()
                    self.type_temp_text(message)
                    self.warning_message = None
                    self._schedule_message_clear()     
                
                case InputState.ERROR:
                    # 错误状态
                    message = message(self.error_message)
                    self._delete_previous_text()
                    self.type_temp_text(message)
                    self.error_message = None
                    self._schedule_message_clear()  
            
                case InputState.IDLE:
                    # 空闲状态，清除所有临时文本
                    self.processing_text = None
                
                case _:
                    # 其他状态
                    self.type_temp_text(message)
    
    def _schedule_message_clear(self):
        """计划清除消息"""
        def clear_message():
            time.sleep(2)  # 警告消息显示2秒
            self.state = InputState.IDLE
            # 警告/错误消息后自动隐藏悬浮窗
            if self.floating_window:
                try:
                    self.floating_window.window.after(0, self.floating_window.hide)
                except Exception:
                    pass
        
        import threading
        threading.Thread(target=clear_message, daemon=True).start()
    
    def show_warning(self, warning_message):
        """显示警告消息"""
        self.warning_message = warning_message
        self.state = InputState.WARNING
    
    def show_error(self, error_message):
        """显示错误消息"""
        self.error_message = error_message
        self.state = InputState.ERROR
    
    def _save_clipboard(self):
        """保存当前剪贴板内容"""
        if self._original_clipboard is None:
            self._original_clipboard = pyperclip.paste()

    def _restore_clipboard(self):
        """恢复原始剪贴板内容"""
        if self._original_clipboard is not None:
            pyperclip.copy(self._original_clipboard)
            self._original_clipboard = None

    def type_text(self, text, error_message=None):
        """将文字输入到当前光标位置
        
        Args:
            text: 要输入的文本或包含文本和错误信息的元组
            error_message: 错误信息
        """
        # 如果text是元组，说明是从process_audio返回的结果
        if isinstance(text, tuple):
            text, error_message = text
            
        if error_message:
            self.show_error(error_message)
            return
            
        if not text:
            # 如果没有文本且不是错误，可能是录音时长不足
            if self.state in (InputState.PROCESSING, InputState.TRANSLATING):
                self.show_warning("录音时长过短，请至少录制1秒")
            return
            
        try:
            logger.info("正在输入转录文本...")
            # 悬浮窗状态模式：仅在悬浮窗显示过程与结果，但最终文本仍写入目标应用（不写状态/✅）
            if getattr(self, 'floating_window', None) and getattr(self.floating_window, 'mode', 'status') == 'status':
                try:
                    self.floating_window.update_status("✅ 完成")
                    if text:
                        self.floating_window.set_text(text)
                except Exception:
                    pass

                # 仅写入最终文本
                write_ok = False
                # 优先：若有目标窗口句柄，尝试 WM_CHAR 写入（不依赖剪贴板/键盘注入）
                write_ok = self._write_text_to_hwnd(text)
                if not write_ok:
                    if self.input_mode == "paste":
                        try:
                            write_ok = self._clipboard_paste_with_backup(text)
                        except Exception as e:
                            logger.warning(f"粘贴最终文本失败，改为直接键入：{e}")
                            write_ok = self._type_text_direct(text)
                    else:
                        write_ok = self._type_text_direct(text)

                if not write_ok:
                    self.show_error("❌ 文本写入失败（已禁用剪贴板回退）。可设置 ALLOW_CLIPBOARD_FALLBACK=true 以启用粘贴回退")
                    return

                # 根据配置恢复原剪贴板
                if os.getenv("KEEP_ORIGINAL_CLIPBOARD", "true").lower() == "true":
                    self._restore_clipboard()

                logger.info("文本输入完成")
                self.state = InputState.IDLE
                return

            # 非状态模式维持原逻辑（会输入状态与✅标记再删除）
            self._delete_previous_text()
            self.type_temp_text(text+" ✅")
            time.sleep(0.5)
            self.temp_text_length = 2
            self._delete_previous_text()

            if os.getenv("KEEP_ORIGINAL_CLIPBOARD", "true").lower() != "true":
                try:
                    pyperclip.copy(text)
                except Exception as e:
                    logger.warning(f"复制结果到剪贴板失败：{e}")
            else:
                self._restore_clipboard()

            logger.info("文本输入完成")
            self.state = InputState.IDLE
        except Exception as e:
            logger.error(f"文本输入失败: {e}")
            self.show_error(f"❌ 文本输入失败: {e}")
    
    def _delete_previous_text(self):
        """删除之前输入的临时文本"""
        # 启用悬浮窗时，不在目标应用删除临时文本
        if getattr(self, 'floating_window', None):
            self.temp_text_length = 0
            return
        if self.temp_text_length > 0:
            for _ in range(self.temp_text_length):
                self.keyboard.press(Key.backspace)
                self.keyboard.release(Key.backspace)

        self.temp_text_length = 0
    
    def type_temp_text(self, text):
        """输入临时状态文本"""
        if not text:
            return
        # 悬浮窗为状态模式：仅更新状态；不向目标应用输入
        if getattr(self, 'floating_window', None) and getattr(self.floating_window, 'mode', 'status') == 'status':
            try:
                self.floating_window.update_status(text)
            except Exception:
                pass
            self.temp_text_length = 0
            return
        
        if self.input_mode == "paste":
            # 将文本复制到剪贴板并粘贴
            try:
                pyperclip.copy(text)
            except Exception as e:
                logger.warning(f"复制临时文本到剪贴板失败，改用直接键入：{e}")
                self.input_mode = "type"
            
            if self.input_mode == "paste":
                with self.keyboard.pressed(self.sysetem_platform):
                    self.keyboard.press('v')
                    self.keyboard.release('v')
            else:
                self._type_text_direct(text)
        else:
            # 直接键入（不占用剪贴板）
            self._type_text_direct(text)

        # 更新临时文本长度
        self.temp_text_length = len(text)

    def _type_text_direct(self, text: str) -> bool:
        """直接键入文本，成功返回 True，失败返回 False。
        Windows 使用 SendInput Unicode，其他平台用 pynput.type。
        若 ALLOW_CLIPBOARD_FALLBACK=true，则在失败时尝试粘贴回退。
        """
        try:
            if os.getenv("SYSTEM_PLATFORM") == "win":
                # Windows 下先尝试目标窗口直接写入
                if self._write_text_to_hwnd(text):
                    return True
                # 如果直接写入失败，再尝试 SendInput
                self._type_text_unicode_windows(text)
            else:
                self.keyboard.type(text)
            return True
        except Exception as e:
            logger.warning(f"直接键入文本失败：{e}")
            # 自动启用剪贴板回退（提高成功率）
            return self._clipboard_paste_with_backup(text)

    def _clipboard_paste_with_backup(self, text: str) -> bool:
        """使用剪贴板粘贴文本，自动备份和恢复原剪贴板内容"""
        original_clipboard = None
        try:
            # 备份当前剪贴板内容
            try:
                original_clipboard = pyperclip.paste()
                logger.debug("已备份原剪贴板内容")
            except Exception as e:
                logger.warning(f"备份剪贴板失败，继续执行: {e}")
            
            # 复制新文本到剪贴板
            logger.info("尝试剪贴板粘贴回退...")
            pyperclip.copy(text)
            
            # 执行粘贴操作
            with self.keyboard.pressed(self.sysetem_platform):
                self.keyboard.press('v')
                self.keyboard.release('v')
            
            # 短暂延迟确保粘贴完成
            time.sleep(0.1)
            
            logger.info("剪贴板粘贴成功")
            return True
            
        except Exception as e:
            logger.error(f"剪贴板粘贴失败：{e}")
            return False
        finally:
            # 恢复原剪贴板内容
            if original_clipboard is not None:
                try:
                    pyperclip.copy(original_clipboard)
                    logger.debug("已恢复原剪贴板内容")
                except Exception as e:
                    logger.warning(f"恢复剪贴板失败: {e}")

    def _write_text_to_hwnd(self, text: str) -> bool:
        """若在 Windows 且拿到目标窗口句柄，使用 WM_CHAR 直接写入。
        成功返回 True；否则 False。
        """
        try:
            if os.getenv("SYSTEM_PLATFORM") != "win":
                return False
            hwnd = None
            if getattr(self, 'floating_window', None):
                hwnd = getattr(self.floating_window, 'target_window_handle', None)
            if not hwnd:
                return False
            user32 = ctypes.WinDLL('user32', use_last_error=True)
            WM_CHAR = 0x0102
            WM_GETTEXTLENGTH = 0x000E
            EM_REPLACESEL = 0x00C2
            EM_SETSEL = 0x00B1
            # 置前，附加输入队列提升成功率
            try:
                foreground = user32.GetForegroundWindow()
                thread_fore = user32.GetWindowThreadProcessId(foreground, None)
                thread_target = user32.GetWindowThreadProcessId(hwnd, None)
                user32.AttachThreadInput(thread_fore, thread_target, True)
            except Exception:
                pass
            try:
                user32.ShowWindow(hwnd, 9)  # SW_RESTORE
                user32.SetForegroundWindow(hwnd)
            except Exception:
                pass

            # 获取窗口类名，优先走 Edit/RichEdit 的 EM_REPLACESEL（更稳，不动剪贴板）
            try:
                get_class_name = getattr(user32, 'GetClassNameW')
                buf = ctypes.create_unicode_buffer(256)
                get_class_name(int(hwnd), buf, 256)
                class_name = buf.value.upper()
            except Exception:
                class_name = ""

            before_len = None
            try:
                if class_name.startswith('EDIT'):
                    before_len = user32.SendMessageW(int(hwnd), WM_GETTEXTLENGTH, 0, 0)
            except Exception:
                pass

            if class_name.startswith('EDIT') or 'RICHEDIT' in class_name:
                try:
                    utext = ctypes.create_unicode_buffer(text)
                    user32.SendMessageW(int(hwnd), EM_REPLACESEL, 1, ctypes.addressof(utext))
                    if before_len is not None:
                        after_len = user32.SendMessageW(int(hwnd), WM_GETTEXTLENGTH, 0, 0)
                        if after_len is not None and int(after_len) >= int(before_len):
                            pass
                    # 无论长度是否可取，认为成功，后续失败会有兜底
                    replaced = True
                except Exception:
                    replaced = False
            else:
                replaced = False

            if not replaced:
                # 回退：发送 UTF-16 单元（通用 WM_CHAR）
                data = text.replace('\r\n', '\n').replace('\r', '\n').encode('utf-16-le')
                for i in range(0, len(data), 2):
                    code_unit = int.from_bytes(data[i:i+2], 'little')
                    if code_unit == 0x000A:
                        code_unit = 0x000D
                    user32.SendMessageW(int(hwnd), WM_CHAR, code_unit, 0)

            try:
                foreground = user32.GetForegroundWindow()
                thread_fore = user32.GetWindowThreadProcessId(foreground, None)
                thread_target = user32.GetWindowThreadProcessId(hwnd, None)
                user32.AttachThreadInput(thread_fore, thread_target, False)
            except Exception:
                pass
            return True
        except Exception as e:
            logger.warning(f"WM_CHAR 写入失败：{e}")
            return False

    def _type_text_unicode_windows(self, text: str):
        """使用 Win32 SendInput 以 Unicode 模式发送文本，支持中文/表情等。"""
        user32 = ctypes.WinDLL('user32', use_last_error=True)

        INPUT_KEYBOARD = 1
        KEYEVENTF_UNICODE = 0x0004
        KEYEVENTF_KEYUP = 0x0002

        # 兼容定义 ULONG_PTR（不同 Python 版本的 wintypes 可能无该定义）
        if ctypes.sizeof(ctypes.c_void_p) == ctypes.sizeof(ctypes.c_ulonglong):
            ULONG_PTR = ctypes.c_ulonglong
        else:
            ULONG_PTR = ctypes.c_ulong

        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [
                ('wVk', wintypes.WORD),
                ('wScan', wintypes.WORD),
                ('dwFlags', wintypes.DWORD),
                ('time', wintypes.DWORD),
                ('dwExtraInfo', ULONG_PTR),
            ]

        class _INPUT_UNION(ctypes.Union):
            _fields_ = [('ki', KEYBDINPUT)]

        class INPUT(ctypes.Structure):
            _anonymous_ = ('u',)
            _fields_ = [('type', wintypes.DWORD), ('u', _INPUT_UNION)]

        LPINPUT = ctypes.POINTER(INPUT)
        user32.SendInput.argtypes = (wintypes.UINT, LPINPUT, ctypes.c_int)
        user32.SendInput.restype = wintypes.UINT

        def send_code_unit(code_unit: int):
            down = INPUT()
            down.type = INPUT_KEYBOARD
            down.ki = KEYBDINPUT(0, code_unit, KEYEVENTF_UNICODE, 0, 0)

            up = INPUT()
            up.type = INPUT_KEYBOARD
            up.ki = KEYBDINPUT(0, code_unit, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, 0, 0)

            arr = (INPUT * 2)(down, up)
            n = user32.SendInput(2, arr, ctypes.sizeof(INPUT))
            if n != 2:
                err = ctypes.get_last_error()
                if err == 87:  # ERROR_INVALID_PARAMETER
                    raise OSError(err, "SendInput 权限不足，可能需要管理员权限或目标窗口不接受输入")
                else:
                    raise OSError(err, ctypes.FormatError(err))

        # 将文本按 UTF-16LE 编码逐个 code unit 发送
        data = text.encode('utf-16-le')
        for i in range(0, len(data), 2):
            code_unit = int.from_bytes(data[i:i+2], 'little')
            if code_unit == 0:
                continue
            send_code_unit(code_unit)
    

    def on_press(self, key):
        """按键按下时的回调 - V2 '按住' 模式"""
        self.pressed_keys.add(key)
        
        # 如果已在录音，或状态不允许开始，则忽略
        if self.is_recording or not self.state.can_start_recording:
            return

        is_translation_hotkey = self.translations_button.issubset(self.pressed_keys)
        is_transcription_hotkey = self.transcriptions_button.issubset(self.pressed_keys)

        # 必须同时按下翻译和转录键才能触发翻译
        if is_translation_hotkey and is_transcription_hotkey:
            self.is_recording = True
            logger.info("翻译热键按下，开始录音...")
            if self.floating_window:
                self.floating_window._show_at_position(self.floating_window.mouse_x, self.floating_window.mouse_y)
            self._save_clipboard()
            self.mute_system_volume()
            self.state = InputState.RECORDING_TRANSLATE
        
        elif is_transcription_hotkey:
            self.is_recording = True
            logger.info("转录热键按下，开始录音...")
            if self.floating_window:
                self.floating_window._show_at_position(self.floating_window.mouse_x, self.floating_window.mouse_y)
            self._save_clipboard()
            self.mute_system_volume()
            self.state = InputState.RECORDING

    def on_release(self, key):
        """按键释放时的回调"""
        if key in self.pressed_keys:
            self.pressed_keys.remove(key)

        is_hotkey_released = not self.transcriptions_button.issubset(self.pressed_keys) and self.is_recording

        if is_hotkey_released:
            self.is_recording = False
            self.restore_system_volume()
            logger.info("热键释放，停止录音...")
            if self.state == InputState.RECORDING_TRANSLATE:
                self.state = InputState.TRANSLATING
            elif self.state == InputState.RECORDING:
                self.state = InputState.PROCESSING
    
    def mute_system_volume(self):
        try:
            sessions = AudioUtilities.GetAllSessions()
            self.original_audio_states.clear()
            for session in sessions:
                if not session.Process:
                    continue
                volume = session.SimpleAudioVolume
                session_id = session.Process.pid
                self.original_audio_states[session_id] = {
                    'volume': volume.GetMasterVolume(),
                    'mute': volume.GetMute()
                }

            fade_duration = 0.3  # seconds
            steps = 10
            delay = fade_duration / steps

            for i in range(steps, -1, -1):
                level = i / steps
                for session in sessions:
                    if session.Process:
                        volume = session.SimpleAudioVolume
                        original_volume = self.original_audio_states.get(session.Process.pid, {}).get('volume', 1.0)
                        volume.SetMasterVolume(original_volume * level, None)
                time.sleep(delay)

        except Exception as e:
            logger.error(f"静音失败: {e}")

    def restore_system_volume(self):
        try:
            if not self.original_audio_states:
                return

            sessions = AudioUtilities.GetAllSessions()
            
            fade_duration = 0.3  # seconds
            steps = 10
            delay = fade_duration / steps

            for i in range(steps + 1):
                level = i / steps
                for session in sessions:
                    if session.Process:
                        session_id = session.Process.pid
                        if session_id in self.original_audio_states:
                            original_state = self.original_audio_states[session_id]
                            volume = session.SimpleAudioVolume
                            volume.SetMasterVolume(original_state['volume'] * level, None)
                time.sleep(delay)

            # 确保恢复到原始的确切状态
            for session in sessions:
                 if session.Process:
                    session_id = session.Process.pid
                    if session_id in self.original_audio_states:
                        original_state = self.original_audio_states[session_id]
                        volume = session.SimpleAudioVolume
                        volume.SetMasterVolume(original_state['volume'], None)
                        volume.SetMute(original_state['mute'], None)

            self.original_audio_states.clear()
        except Exception as e:
            logger.error(f"恢复音量失败: {e}")

    def start_listening(self):
        """开始监听键盘事件"""
        with Listener(on_press=self.on_press, on_release=self.on_release) as listener:
            listener.join()

    def reset_state(self):
        """重置所有状态和临时文本"""
        # 清除临时文本
        self._delete_previous_text()
        
        # 恢复剪贴板
        self._restore_clipboard()
        
        # 重置状态标志
        self.option_pressed = False
        self.shift_pressed = False
        self.option_press_time = None
        self.is_checking_duration = False
        self.has_triggered = False
        self.processing_text = None
        self.error_message = None
        self.warning_message = None
        
        # 设置为空闲状态
        self.state = InputState.IDLE

 