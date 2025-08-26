import tkinter as tk
from tkinter import ttk
import threading
import time
from pynput import mouse
from ..utils.logger import logger
import os


class FloatingWindow:
    def __init__(self, on_record_start, on_record_stop, on_translate_start, on_translate_stop, on_write=None, on_optimize=None):
        """初始化悬浮窗
        
        Args:
            on_record_start: 开始录音回调
            on_record_stop: 停止录音回调  
            on_translate_start: 开始翻译录音回调
            on_translate_stop: 停止翻译录音回调
        """
        self.on_record_start = on_record_start
        self.on_record_stop = on_record_stop
        self.on_translate_start = on_translate_start
        self.on_translate_stop = on_translate_stop
        self.on_write = on_write
        self.on_optimize = on_optimize
        
        # 模式：status 仅状态显示；full 完整功能
        self.mode = os.getenv("FLOATING_WINDOW_MODE", "status").lower()
        # 波形增益，放大可视振幅（例如 5 表示 5 倍）
        try:
            self.wave_gain = float(os.getenv("WAVE_GAIN", "5"))
        except Exception:
            self.wave_gain = 5.0
        
        # 使用项目内置的SVG图标
        self.icon_assets = {
            'mic': 'assets/icons/mic.svg',
            'voice': 'assets/icons/voice.svg', 
            'waveform': 'assets/icons/waveform.svg',
            'spinner': 'assets/icons/spinner.svg'
        }
        
        # 自定义图标路径（可选，优先级更高）
        self.custom_icon_path = os.getenv("CUSTOM_ICON_PATH", "")
        self.custom_icon_image = None
        if self.custom_icon_path and os.path.exists(self.custom_icon_path):
            try:
                from PIL import Image, ImageTk
                img = Image.open(self.custom_icon_path).resize((50, 50), Image.Resampling.LANCZOS)
                self.custom_icon_image = ImageTk.PhotoImage(img)
                logger.info(f"加载自定义图标: {self.custom_icon_path}")
            except Exception as e:
                logger.warning(f"加载自定义图标失败: {e}")
                self.custom_icon_image = None

        # 悬浮窗状态
        self.window = None
        self.is_recording = False
        self.is_translating = False
        self.is_visible = False
        self.follow_mouse = True
        self.target_window_handle = None  # 记录呼出时鼠标所在窗口句柄（Windows）
        
        # 鼠标位置
        self.mouse_x = 0
        self.mouse_y = 0
        
        # 创建悬浮窗
        self._create_window()
        
        # 启动鼠标监听
        self._start_mouse_listener()
        
        # 添加快捷键绑定
        self.window.bind('<Control-i>', lambda e: self._show_window_info())
        
        # 常驻显示模式：创建后立即显示在屏幕右下角
        if self.mode == "status":
            self._show_persistent_icon()
    
    def _show_window_info(self):
        """显示当前窗口状态信息"""
        try:
            focused = self.window.focus_get()
            if focused:
                info = f"当前焦点控件: {focused.__class__.__name__}\n"
                info += f"是否为文本框: {isinstance(focused, tk.Text)}\n"
                info += f"是否可编辑: {focused.cget('state') != 'disabled' if hasattr(focused, 'cget') else '未知'}"
                if self.mode != 'status':
                    self.status_label.config(text=info)
                logger.info(info)
            else:
                logger.info("当前窗口没有焦点控件")
        except Exception as e:
            logger.error(f"获取窗口状态失败: {e}")

    def _create_window(self):
        """创建悬浮窗"""
        self.window = tk.Tk()
        self.window.title("语音输入")
        # 统一管理窗口尺寸，供显示时使用
        if self.mode == "status":
            self.window_width = 140  # 胶囊形状尺寸
            self.window_height = 60
        else:
            self.window_width = 400
            self.window_height = 300
        self.window.geometry(f"{self.window_width}x{self.window_height}")
        # Windows 高分屏缩放兼容
        try:
            import ctypes
            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(1)
            except Exception:
                ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass
        self.window.resizable(False, False)
        
        # 设置窗口属性
        self.window.attributes('-topmost', True)  # 置顶
        self.window.overrideredirect(True)        # 无边框
        
        # 新的透明方案：使用一种特殊的颜色进行抠图，以支持抗锯齿
        # 这种颜色理论上不会在UI元素中出现
        self.transparent_color = '#010203'
        self.window.attributes('-transparentcolor', self.transparent_color)
        
        # 设置窗口样式
        self.window.configure(bg=self.transparent_color)
        
        # 创建主框架
        main_frame = tk.Frame(self.window, bg=self.transparent_color, padx=10, pady=10)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        if self.mode == "status":
            # 胶囊形状的现代图标模式 - 使用更大的画布来实现抗锯齿
            canvas_scale = 2  # 2倍分辨率用于抗锯齿
            self.canvas_scale = canvas_scale
            self.icon_canvas = tk.Canvas(
                main_frame, width=120, height=40,
                bg=self.transparent_color, highlightthickness=0, cursor='hand2',
                bd=0, relief='flat'
            )
            # 尝试启用抗锯齿（如果支持）
            try:
                self.icon_canvas.configure(scrollregion=(0, 0, 120*canvas_scale, 40*canvas_scale))
            except:
                pass
            self.icon_canvas.pack(expand=True)
            self.icon_canvas.bind("<Button-1>", lambda e: self._toggle_recording())
            self.icon_canvas.bind("<Enter>", self._on_icon_hover)
            self.icon_canvas.bind("<Leave>", self._on_icon_leave)

            # 动画和悬浮状态
            self._anim_phase = 0
            self._anim_job = None
            self._is_hovering = False
            self._hover_text_job = None
            # 延迟绘制，确保Canvas已经准备好
            self.window.after(100, self._draw_idle_icon)
            
            # 隐藏状态标签等复杂UI元素
            self.status_label = None
            self.display_widget = None
            self.time_label = None
            self.level_canvas = None
            self._level = 0.0
            self._wave_samples = []
            self._wave_capacity = 512
        else:
            # 状态标签
            self.status_label = tk.Label(
                main_frame, 
                text="准备就绪", 
                bg='#2c3e50', 
                fg='#ecf0f1',
                font=('Arial', 10)
            )
            self.status_label.pack(pady=(0, 5))

            # 文本编辑框（显示/编辑转录结果）
            text_frame = tk.Frame(main_frame, bg='#2c3e50')
            text_frame.pack(fill=tk.BOTH, expand=True)
            self.text_widget = tk.Text(
                text_frame,
                height=4,
                wrap=tk.WORD,
                bg='#34495e',
                fg='#ecf0f1',
                insertbackground='#ecf0f1',
                relief=tk.FLAT,
                font=('Arial', 10)
            )
            self.text_widget.pack(fill=tk.BOTH, expand=True)

            # 按钮框架
            button_frame = tk.Frame(main_frame, bg='#2c3e50')
            button_frame.pack(fill=tk.X, pady=(10, 4))
            
            # 录音按钮
            self.record_button = tk.Button(
                button_frame,
                text="🎤 录音",
                command=self._toggle_recording,
                bg='#3498db',
                fg='white',
                font=('Arial', 10, 'bold'),
                relief=tk.FLAT,
                padx=15,
                pady=5
            )
            self.record_button.pack(side=tk.LEFT, padx=(0, 5))
            
            # 翻译按钮
            self.translate_button = tk.Button(
                button_frame,
                text="🌐 翻译",
                command=self._toggle_translation,
                bg='#e74c3c',
                fg='white',
                font=('Arial', 10, 'bold'),
                relief=tk.FLAT,
                padx=15,
                pady=5
            )
            self.translate_button.pack(side=tk.LEFT, padx=(0, 6))

            # 优化按钮
            self.optimize_button = tk.Button(
                button_frame,
                text="✨ 优化",
                command=self._optimize_text,
                bg='#8e44ad',
                fg='white',
                font=('Arial', 10, 'bold'),
                relief=tk.FLAT,
                padx=15,
                pady=5
            )
            self.optimize_button.pack(side=tk.LEFT, padx=(0, 6))

            # 写入按钮
            self.write_button = tk.Button(
                button_frame,
                text="✍️ 写入",
                command=self._write_text,
                bg='#27ae60',
                fg='white',
                font=('Arial', 10, 'bold'),
                relief=tk.FLAT,
                padx=15,
                pady=5
            )
            self.write_button.pack(side=tk.LEFT)
        
        # 关闭按钮
        close_button = tk.Button(
            main_frame,
            text="✕",
            command=self._hide_window,
            bg='#e74c3c',
            fg='white',
            font=('Arial', 8),
            relief=tk.FLAT,
            width=3
        )
        close_button.pack(side=tk.RIGHT, anchor=tk.NE)
        
        # 绑定鼠标事件（左键拖动；右键不做任何操作）
        self.window.bind('<Button-1>', self._on_mouse_down)
        self.window.bind('<B1-Motion>', self._on_mouse_drag)
        # self.window.bind('<Button-3>', lambda e: None)
        
        # status 模式不需要复杂的计时器，只在录音时启动动画
        if self.mode != "status":
            # 启动渲染循环（不依赖计时器），初始隐藏
            try:
                self.window.after(100, self._tick_timer)
            except Exception:
                pass
            # 默认启动计时刷新，便于测试与可见性（录音开始会重置显示状态）
            try:
                self._start_timer()
            except Exception:
                pass
            self.window.withdraw()
        # status 模式保持可见，不隐藏
    
    def _start_mouse_listener(self):
        """启动鼠标监听"""
        def on_move(x, y):
            self.mouse_x = x
            self.mouse_y = y
            # status 模式的图标是固定的，不跟随鼠标
        
        def on_click(x, y, button, pressed):
            # 忽略所有右键事件（不显示、不隐藏）
            return
        
        # 启动鼠标监听线程
        mouse_listener = mouse.Listener(
            on_move=on_move,
            on_click=on_click
        )
        mouse_listener.start()
    
    def _show_persistent_icon(self):
        """显示常驻图标在屏幕右下角"""
        if self.window:
            screen_width = self.window.winfo_screenwidth()
            screen_height = self.window.winfo_screenheight()
            
            # 计算任务栏列数
            taskbar_columns = screen_width // (self.window_width + 20)  # 20px为图标间距
            
            # 计算居中位置
            total_width = taskbar_columns * (self.window_width + 20) - 20  # 减去最后一个间距
            start_x = (screen_width - total_width) // 2
            
            # 固定在任务栏上方中间位置
            pos_x = start_x + (taskbar_columns // 2) * (self.window_width + 20)
            pos_y = screen_height - self.window_height - 80  # 留出任务栏空间
            
            self.window.geometry(f"{self.window_width}x{self.window_height}+{pos_x}+{pos_y}")
            self.window.deiconify()
            self.window.lift()  # 确保显示在最前
            self.window.attributes('-topmost', True)  # 设置置顶
            self.is_visible = True
            
            # 防止窗口被系统隐藏，定期检查可见性
            self._start_visibility_check()

    def _show_at_position(self, x, y):
        """在指定位置显示悬浮窗（status模式忽略此方法，使用固定位置）"""
        if self.mode == "status":
            # status 模式图标固定不动
            return
            
        if self.window:
            # 计算窗口位置（避免超出屏幕边界）；默认出现在鼠标上方/右侧更可见
            screen_width = self.window.winfo_screenwidth()
            screen_height = self.window.winfo_screenheight()
            
            # 窗口尺寸（使用初始化时的统一尺寸）
            window_width = self.window_width
            window_height = self.window_height
            
            # 默认放在鼠标上方 12px，若越界则放在下方；X 右侧 12px
            pos_x = x + 12
            pos_y = y - window_height - 12
            if pos_x + window_width > screen_width:
                pos_x = screen_width - window_width - 8
            if pos_x < 0:
                pos_x = 8
            if pos_y < 0:
                pos_y = y + 12
            if pos_y + window_height > screen_height:
                pos_y = screen_height - window_height - 8
            
            self.window.geometry(f"{window_width}x{window_height}+{pos_x}+{pos_y}")
            self.window.deiconify()
            self.is_visible = True
            self.follow_mouse = False  # 不跟随鼠标移动
            # 记录鼠标所在窗口句柄 + 当前前台窗口句柄（Windows）
            try:
                import ctypes
                from ctypes import wintypes
                user32 = ctypes.WinDLL('user32', use_last_error=True)
                class POINT(ctypes.Structure):
                    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]
                pt = POINT(int(x), int(y))
                hwnd_from_point = user32.WindowFromPoint(pt)
                hwnd_foreground = user32.GetForegroundWindow()
                # 自身窗口句柄
                self_hwnd = user32.FindWindowW(None, "语音输入")
                # 选择有效目标：优先鼠标下窗口，其次前台窗口，均需排除自身
                target = None
                if hwnd_from_point and hwnd_from_point != self_hwnd:
                    target = hwnd_from_point
                elif hwnd_foreground and hwnd_foreground != self_hwnd:
                    target = hwnd_foreground
                self.target_window_handle = target
            except Exception:
                self.target_window_handle = None
    
    def _hide_window(self):
        """隐藏悬浮窗（status模式不隐藏）"""
        if self.window and self.mode != "status":
            self.window.withdraw()
            self.is_visible = False
            self.follow_mouse = False
        elif self.mode == "status":
            logger.debug("status模式下不隐藏常驻图标")
    
    def _update_position(self):
        """更新悬浮窗位置（已废弃，不再跟随鼠标）"""
        pass
    
    def _on_mouse_down(self, event):
        """鼠标按下事件"""
        self.window.focus_set()
        # 确保文本输入框获得焦点
        if getattr(self, 'text_widget', None):
            try:
                self.text_widget.focus_set()
            except Exception:
                pass
    
    def _on_mouse_drag(self, event):
        """鼠标拖拽事件"""
        if self.window:
            x = self.window.winfo_x() + event.x
            y = self.window.winfo_y() + event.y
            self.window.geometry(f"+{x}+{y}")

    # === 新增：status 模式胶囊图标 ===
    def _on_icon_hover(self, event):
        """鼠标悬停在图标上"""
        self._is_hovering = True
        if not self.is_recording:  # 只在非录音状态显示悬浮提示
            self._show_hover_text()
        
    def _on_icon_leave(self, event):
        """鼠标离开图标"""
        self._is_hovering = False
        if self._hover_text_job:
            self.window.after_cancel(self._hover_text_job)
            self._hover_text_job = None
        if not self.is_recording:
            self._draw_idle_icon()
    
    def _show_hover_text(self):
        """显示悬浮提示文本 - 简洁版本"""
        if not self._is_hovering or self.is_recording:
            return
        
        c = getattr(self, 'icon_canvas', None)
        if not c:
            return
            
        c.delete("all")
        w, h = 120, 40
        center_x, center_y = w // 2, h // 2
        
        # 使用PIL创建悬浮状态的抗锯齿图像
        try:
            from PIL import Image, ImageDraw, ImageTk, ImageFont, ImageFilter
            
            # 创建高分辨率图像
            scale = 4  # 悬浮状态用4倍就够了，提高性能
            img_w, img_h = w * scale, h * scale
            img = Image.new('RGBA', (img_w, img_h), self.transparent_color)
            draw = ImageDraw.Draw(img)
            
            # 绘制稍微亮一点的胶囊背景（悬浮效果）
            hover_bg = (74, 85, 104, 255)  # #4a5568 稍微亮一点
            margin = int(2 * scale)
            radius = (img_h - 2*margin) // 2
            
            # 绘制胶囊形状
            try:
                draw.rounded_rectangle(
                    [margin, margin, img_w - margin, img_h - margin],
                    radius=radius, fill=hover_bg
                )
            except AttributeError:
                # 兼容老版本PIL
                draw.rectangle([margin + radius, margin, img_w - margin - radius, img_h - margin], fill=hover_bg)
                draw.ellipse([margin, margin, margin + 2*radius, img_h - margin], fill=hover_bg)
                draw.ellipse([img_w - margin - 2*radius, margin, img_w - margin, img_h - margin], fill=hover_bg)
            
            # 绘制文字（使用系统字体）
            text = "Click to start dictating"
            text_color = (226, 232, 240, 255)  # #e2e8f0
            
            # 尝试使用更好的字体
            try:
                font = ImageFont.truetype("arial.ttf", int(10 * scale))
            except:
                try:
                    font = ImageFont.truetype("calibri.ttf", int(10 * scale))
                except:
                    font = ImageFont.load_default()
            
            # 获取文字尺寸并居中绘制
            try:
                bbox = draw.textbbox((0, 0), text, font=font)
                text_w = bbox[2] - bbox[0]
                text_h = bbox[3] - bbox[1]
                text_x = (img_w - text_w) // 2
                text_y = (img_h - text_h) // 2
                draw.text((text_x, text_y), text, fill=text_color, font=font)
            except:
                # 回退到简单的文字绘制
                draw.text((img_w//2, img_h//2), text, fill=text_color, anchor="mm")
            
            # 缩放到最终尺寸
            img_final = img.resize((w, h), Image.Resampling.LANCZOS)
            
            # 轻微模糊平滑边缘
            try:
                img_final = img_final.filter(ImageFilter.GaussianBlur(radius=0.2))
            except:
                pass
            
            self.hover_icon_image = ImageTk.PhotoImage(img_final)
            c.create_image(center_x, center_y, image=self.hover_icon_image)
            
        except ImportError:
            # PIL不可用时的简单回退
            # 保持原始胶囊形状，只显示文字
            bg_color = '#4a5568'  # 稍微亮一点的背景
            margin = 2
            
            # 绘制胶囊背景（无边框）
            c.create_rectangle(margin, margin, w-margin, h-margin, 
                             fill=bg_color, outline='', width=0)
            radius = (h - 2*margin) // 2
            c.create_oval(margin, margin, 2*radius + margin, h-margin, 
                         fill=bg_color, outline='', width=0)
            c.create_oval(w - 2*radius - margin, margin, w-margin, h-margin, 
                         fill=bg_color, outline='', width=0)
            
            # 只显示文字，无边框
            c.create_text(w//2, h//2, text="Click to start dictating", 
                         fill='#e2e8f0', font=('Arial', 8), anchor='center')
        
        # 定时恢复到静止状态
        self._hover_text_job = self.window.after(2000, lambda: self._draw_idle_icon() if not self.is_recording else None)
    def _start_visibility_check(self):
        """定期检查窗口可见性，防止被系统隐藏"""
        if self.mode != "status":
            return
        def _check():
            try:
                if self.window:
                    # 检查窗口是否还在屏幕上
                    if not self.window.winfo_viewable() or not self.is_visible:
                        # 窗口被隐藏，重新显示
                        logger.warning("检测到图标窗口被隐藏，重新显示")
                        self.window.deiconify()
                        self.window.lift()
                        self.window.attributes('-topmost', True)
                        self.is_visible = True
                        # 重新绘制图标
                        if hasattr(self, 'icon_canvas'):
                            if self.is_recording:
                                self._draw_recording_icon()
                            else:
                                self._draw_idle_icon()
                    else:
                        # 确保置顶属性
                        self.window.attributes('-topmost', True)
                # 每3秒检查一次（更频繁）
                self.window.after(3000, _check)
            except Exception as e:
                logger.error(f"可见性检查失败: {e}")
                # 出错时也要继续检查
                if self.window:
                    self.window.after(3000, _check)
        # 启动检查
        self.window.after(3000, _check)

    def _draw_idle_icon(self):
        """绘制静止状态的胶囊图标 - 使用PIL实现抗锯齿"""
        c = getattr(self, 'icon_canvas', None)
        if not c:
            logger.warning("icon_canvas 不存在")
            return
        
        try:
            c.delete("all")
            w, h = 120, 40
            center_x, center_y = w // 2, h // 2
            
            # 如果有自定义图标，优先使用
            if self.custom_icon_image:
                c.create_image(center_x, center_y, image=self.custom_icon_image)
                logger.debug("使用自定义图标绘制完成")
                return
            
            # 使用PIL创建超高质量抗锯齿图像
            try:
                from PIL import Image, ImageDraw, ImageTk, ImageFilter
                
                # 创建超高分辨率图像用于抗锯齿
                scale = 8  # 8倍分辨率，更强的抗锯齿
                img_w, img_h = w * scale, h * scale
                img = Image.new('RGBA', (img_w, img_h), self.transparent_color)  # 使用特殊透明色作为背景
                
                # 创建绘制对象
                draw = ImageDraw.Draw(img)
                
                # 绘制胶囊形状 - 使用更精确的方法
                bg_color = (55, 65, 81, 255)  # #374151
                margin = int(2 * scale)
                radius = (img_h - 2*margin) // 2
                
                # 方法1：使用PIL的圆角矩形
                try:
                    draw.rounded_rectangle(
                        [margin, margin, img_w - margin, img_h - margin],
                        radius=radius, fill=bg_color
                    )
                except AttributeError:
                    # 方法2：手动绘制完美胶囊（兼容老版本PIL）
                    # 中间矩形
                    draw.rectangle([margin + radius, margin, img_w - margin - radius, img_h - margin], fill=bg_color)
                    # 左半圆
                    draw.ellipse([margin, margin, margin + 2*radius, img_h - margin], fill=bg_color)
                    # 右半圆
                    draw.ellipse([img_w - margin - 2*radius, margin, img_w - margin, img_h - margin], fill=bg_color)
                
                # 绘制麦克风图标
                mic_x = 20 * scale
                mic_y = center_y * scale
                mic_color = (209, 213, 219, 255)  # #d1d5db
                
                # 麦克风主体（椭圆）
                draw.ellipse([mic_x - 3*scale, mic_y - 6*scale, 
                             mic_x + 3*scale, mic_y + 2*scale], fill=mic_color)
                # 麦克风杆
                draw.rectangle([mic_x - 1*scale, mic_y + 2*scale,
                               mic_x + 1*scale, mic_y + 8*scale], fill=mic_color)
                
                # 不绘制静态波形，保持简洁的椭圆按钮
                pass
                
                # 多步缩放以获得最佳抗锯齿效果
                # 第一步：从8x缩放到4x
                img_4x = img.resize((w * 4, h * 4), Image.Resampling.LANCZOS)
                # 第二步：从4x缩放到2x
                img_2x = img_4x.resize((w * 2, h * 2), Image.Resampling.LANCZOS)
                # 第三步：从2x缩放到最终尺寸
                img_final = img_2x.resize((w, h), Image.Resampling.LANCZOS)
                
                # 可选：添加轻微的高斯模糊来进一步平滑边缘
                try:
                    img_final = img_final.filter(ImageFilter.GaussianBlur(radius=0.3))
                except:
                    pass  # 如果不支持滤镜则跳过
                
                self.idle_icon_image = ImageTk.PhotoImage(img_final)
                c.create_image(center_x, center_y, image=self.idle_icon_image)
                
                logger.debug("使用PIL绘制静止胶囊图标完成")
                return
                
            except ImportError:
                logger.warning("PIL不可用，使用Tkinter绘制")
            except Exception as e:
                logger.warning(f"PIL绘制失败: {e}，回退到Tkinter")
            
            # 回退到原始Tkinter绘制方法
            self._draw_idle_icon_tkinter()
            
        except Exception as e:
            logger.error(f"绘制静止图标失败: {e}")
    
    def _draw_idle_icon_tkinter(self):
        """使用Tkinter绘制静止图标（回退方法）"""
        c = self.icon_canvas
        w, h = 120, 40
        center_x, center_y = w // 2, h // 2
        
        # 原始Tkinter绘制逻辑
        bg_color = '#374151'
        margin = 2
        
        # 绘制胶囊背景
        c.create_rectangle(margin, margin, w-margin, h-margin, 
                         fill=bg_color, outline='', width=0)
        
        radius = (h - 2*margin) // 2
        c.create_oval(margin, margin, 2*radius + margin, h-margin, 
                     fill=bg_color, outline='', width=0)
        c.create_oval(w - 2*radius - margin, margin, w-margin, h-margin, 
                     fill=bg_color, outline='', width=0)
        
        # 绘制麦克风图标
        mic_x = 20
        mic_y = center_y
        mic_color = '#d1d5db'
        
        c.create_oval(mic_x - 3, mic_y - 6, mic_x + 3, mic_y + 2, 
                     fill=mic_color, outline='')
        c.create_rectangle(mic_x - 1, mic_y + 2, mic_x + 1, mic_y + 8, 
                         fill=mic_color, outline='')
        c.create_arc(mic_x - 5, mic_y + 6, mic_x + 5, mic_y + 12,
                    start=0, extent=180, outline=mic_color, width=1, style='arc')
        
        # 不绘制静态波形，保持简洁的椭圆按钮
        pass

    def _start_recording_anim(self):
        """开始录音动画"""
        logger.info("开始录音动画")
        if getattr(self, '_anim_job', None):
            self.window.after_cancel(self._anim_job)
        self._anim_job = None
        self._anim_phase = 0  # 重置动画相位
        self._anim_step()
        
    def _anim_step(self):
        """动画步进函数 - 优化流畅度"""
        if not hasattr(self, 'icon_canvas') or not self.icon_canvas:
            logger.warning("动画步进：icon_canvas 不存在")
            return
            
        # 更精细的动画相位控制
        self._anim_phase = (self._anim_phase + 1) % 60  # 增加到60帧循环，更平滑
        logger.debug(f"动画步进：相位={self._anim_phase}, 录音状态={self.is_recording}")
        
        if self.is_recording:
            self._draw_recording_icon()
            # 提高帧率：从100ms改为33ms（约30FPS），更流畅
            self._anim_job = self.window.after(33, self._anim_step)
        else:
            self._draw_idle_icon()
            self._anim_job = None

    def _draw_recording_icon(self):
        """绘制录音状态的胶囊动画图标 - 使用PIL实现抗锯齿"""
        c = getattr(self, 'icon_canvas', None)
        if not c:
            logger.warning("录音动画：icon_canvas 不存在")
            return
            
        try:
            c.delete("all")
            w, h = 120, 40
            center_x, center_y = w // 2, h // 2
            
            # 如果有自定义图标，在周围添加录音动画效果
            if self.custom_icon_image:
                pulse = 1.0 + 0.1 * abs((self._anim_phase % 10) - 5) / 5
                border_width = int(2 * pulse)
                
                c.create_oval(0, 0, h, h, outline='#ef4444', width=border_width, fill='')
                c.create_oval(w - h, 0, w, h, outline='#ef4444', width=border_width, fill='')
                
                c.create_image(center_x, center_y, image=self.custom_icon_image)
                logger.debug(f"使用自定义图标录音动画绘制完成，动画相位: {self._anim_phase}")
                return
            
            # 使用PIL创建超高质量抗锯齿录音图像
            try:
                from PIL import Image, ImageDraw, ImageTk, ImageFilter
                
                # 创建超高分辨率图像用于抗锯齿
                scale = 8  # 8倍分辨率，更强的抗锯齿
                img_w, img_h = w * scale, h * scale
                img = Image.new('RGBA', (img_w, img_h), self.transparent_color)  # 使用特殊透明色作为背景
                draw = ImageDraw.Draw(img)
                
                # 脉动效果
                pulse = 1.0 + 0.03 * abs((self._anim_phase % 12) - 6) / 6
                
                # 绘制录音状态胶囊形状 - 使用更精确的方法
                bg_color = (220, 38, 38, 255)  # #dc2626
                margin = int(2 * scale)
                radius = (img_h - 2*margin) // 2
                
                # 方法1：使用PIL的圆角矩形
                try:
                    draw.rounded_rectangle(
                        [margin, margin, img_w - margin, img_h - margin],
                        radius=radius, fill=bg_color
                    )
                except AttributeError:
                    # 方法2：手动绘制完美胶囊（兼容老版本PIL）
                    # 中间矩形
                    draw.rectangle([margin + radius, margin, img_w - margin - radius, img_h - margin], fill=bg_color)
                    # 左半圆
                    draw.ellipse([margin, margin, margin + 2*radius, img_h - margin], fill=bg_color)
                    # 右半圆
                    draw.ellipse([img_w - margin - 2*radius, margin, img_w - margin, img_h - margin], fill=bg_color)
                
                # 绘制发光效果
                glow_colors = [(252, 165, 165, 180), (248, 113, 113, 120), (239, 68, 68, 80)]
                glow_intensity = int((self._anim_phase % 8) / 2)
                glow_color = glow_colors[glow_intensity % len(glow_colors)]
                glow_offset = int((1 + pulse) * scale)
                
                # 外圈发光
                draw.rounded_rectangle(
                    [margin - glow_offset, margin - glow_offset, 
                     img_w - margin + glow_offset, img_h - margin + glow_offset],
                    radius=radius + glow_offset, outline=glow_color, width=2*scale
                )
                
                # 绘制白色麦克风图标
                mic_x = 20 * scale
                mic_y = center_y * scale
                mic_color = (255, 255, 255, 255)  # 白色
                
                # 麦克风主体（椭圆）
                draw.ellipse([mic_x - 3*scale, mic_y - 6*scale, 
                             mic_x + 3*scale, mic_y + 2*scale], fill=mic_color)
                # 麦克风杆
                draw.rectangle([mic_x - 1*scale, mic_y + 2*scale,
                               mic_x + 1*scale, mic_y + 8*scale], fill=mic_color)
                
                # 绘制动态波形 - 使用真实音频电平数据
                import math
                wave_x = (center_x + 8) * scale
                wave_color = (255, 255, 255, 255)  # 白色
                
                # 获取当前音频电平 - 增加幅度
                current_level = getattr(self, '_level', 0.0) * self.wave_gain
                current_level = max(0.0, min(1.0, current_level))  # 限制在0-1之间
                
                # 基础波形高度 - 增加基础高度
                base_heights = [4, 8, 6, 12, 8, 10, 4]  # 基础高度翻倍
                
                # 如果有音频信号，使用实时数据；否则使用低强度动画
                if current_level > 0.01:  # 有声音输入
                    for i, base_height in enumerate(base_heights):
                        # 使用真实音频电平 + 轻微的频率差异
                        freq_variation = 1.0 + (i - 3) * 0.15  # 增加频率差异
                        level_variation = current_level * freq_variation
                        level_variation = max(0.2, min(1.0, level_variation))  # 最小高度20%
                        
                        # 添加轻微的时间延迟模拟频谱
                        time_offset = self._anim_phase * 0.1 + i * 0.2
                        smooth_factor = 0.8 + 0.2 * math.sin(time_offset)
                        
                        final_height = base_height * level_variation * smooth_factor
                        bar_height = int(final_height * scale)
                        
                        x = wave_x + i * 3 * scale
                        y_top = mic_y - bar_height // 2
                        y_bottom = mic_y + bar_height // 2
                        
                        # 绘制圆角矩形波形条
                        try:
                            corner_radius = int(1 * scale)
                            draw.rounded_rectangle([x, y_top, x + 2*scale, y_bottom], 
                                                 radius=corner_radius, fill=wave_color)
                        except AttributeError:
                            draw.rectangle([x, y_top, x + 2*scale, y_bottom], fill=wave_color)
                else:
                    # 静音时显示低强度的待机动画
                    for i, base_height in enumerate(base_heights):
                        time_factor = (self._anim_phase * 0.1 + i * 0.5)
                        idle_amplitude = 0.3 + 0.2 * math.sin(time_factor)  # 增加待机波动
                        
                        final_height = base_height * idle_amplitude
                        bar_height = int(final_height * scale)
                        
                        x = wave_x + i * 3 * scale
                        y_top = mic_y - bar_height // 2
                        y_bottom = mic_y + bar_height // 2
                        
                        try:
                            corner_radius = int(1 * scale)
                            draw.rounded_rectangle([x, y_top, x + 2*scale, y_bottom], 
                                                 radius=corner_radius, fill=wave_color)
                        except AttributeError:
                            draw.rectangle([x, y_top, x + 2*scale, y_bottom], fill=wave_color)
                
                # 录音指示点 - 更自然的脉动
                import math
                dot_time = self._anim_phase * 0.3  # 慢一点的脉动
                dot_alpha = (math.sin(dot_time) + 1) / 2  # 0-1之间的平滑脉动
                
                # 颜色渐变：白色到淡红色
                white_factor = dot_alpha
                red_factor = 1 - dot_alpha
                dot_color = (
                    int(255 * white_factor + 252 * red_factor),
                    int(255 * white_factor + 165 * red_factor), 
                    int(255 * white_factor + 165 * red_factor),
                    255
                )
                
                # 大小脉动
                dot_size = int((2 + 2 * dot_alpha) * scale)  # 2-4之间变化
                dot_x = (w - 12) * scale
                
                draw.ellipse([dot_x - dot_size, mic_y - dot_size,
                             dot_x + dot_size, mic_y + dot_size], fill=dot_color)
                
                # 多步缩放以获得最佳抗锯齿效果
                # 第一步：从8x缩放到4x
                img_4x = img.resize((w * 4, h * 4), Image.Resampling.LANCZOS)
                # 第二步：从4x缩放到2x
                img_2x = img_4x.resize((w * 2, h * 2), Image.Resampling.LANCZOS)
                # 第三步：从2x缩放到最终尺寸
                img_final = img_2x.resize((w, h), Image.Resampling.LANCZOS)
                
                # 可选：添加轻微的高斯模糊来进一步平滑边缘
                try:
                    img_final = img_final.filter(ImageFilter.GaussianBlur(radius=0.3))
                except:
                    pass  # 如果不支持滤镜则跳过
                
                # 存储图像引用以防止垃圾回收
                self.recording_icon_image = ImageTk.PhotoImage(img_final)
                c.create_image(center_x, center_y, image=self.recording_icon_image)
                
                logger.debug(f"使用PIL绘制录音胶囊图标完成，动画相位: {self._anim_phase}")
                return
                
            except ImportError:
                logger.warning("PIL不可用，使用Tkinter绘制")
            except Exception as e:
                logger.warning(f"PIL绘制失败: {e}，回退到Tkinter")
            
            # 回退到原始Tkinter绘制方法
            self._draw_recording_icon_tkinter()
            
        except Exception as e:
            logger.error(f"绘制录音图标失败: {e}")
    
    def _draw_recording_icon_tkinter(self):
        """使用Tkinter绘制录音图标（回退方法）"""
        c = self.icon_canvas
        w, h = 120, 40
        center_x, center_y = w // 2, h // 2
        
        # 原始Tkinter绘制逻辑
        bg_color = '#dc2626'
        pulse = 1.0 + 0.03 * abs((self._anim_phase % 12) - 6) / 6
        margin = 2
        
        # 绘制胶囊背景
        c.create_rectangle(margin, margin, w-margin, h-margin, 
                         fill=bg_color, outline='', width=0)
        
        radius = (h - 2*margin) // 2
        c.create_oval(margin, margin, 2*radius + margin, h-margin, 
                     fill=bg_color, outline='', width=0)
        c.create_oval(w - 2*radius - margin, margin, w-margin, h-margin, 
                     fill=bg_color, outline='', width=0)
        
        # 发光效果
        glow_colors = ['#fca5a5', '#f87171', '#ef4444']
        glow_intensity = int((self._anim_phase % 8) / 2)
        glow_color = glow_colors[glow_intensity % len(glow_colors)]
        glow_offset = int(1 + pulse)
        
        c.create_oval(margin - glow_offset, margin - glow_offset, 
                     2*radius + margin + glow_offset, h - margin + glow_offset, 
                     outline=glow_color, width=1, fill='')
        c.create_oval(w - 2*radius - margin - glow_offset, margin - glow_offset, 
                     w - margin + glow_offset, h - margin + glow_offset, 
                     outline=glow_color, width=1, fill='')
        
        # 绘制白色麦克风图标
        mic_x = 20
        mic_y = center_y
        mic_color = 'white'
        
        c.create_oval(mic_x - 3, mic_y - 6, mic_x + 3, mic_y + 2, 
                     fill=mic_color, outline='')
        c.create_rectangle(mic_x - 1, mic_y + 2, mic_x + 1, mic_y + 8, 
                         fill=mic_color, outline='')
        c.create_arc(mic_x - 5, mic_y + 6, mic_x + 5, mic_y + 12,
                    start=0, extent=180, outline=mic_color, width=1, style='arc')
        
        # 绘制动态波形 - 使用真实音频电平数据
        import math
        wave_x = center_x + 8
        wave_color = 'white'
        
        # 获取当前音频电平 - 增加幅度
        current_level = getattr(self, '_level', 0.0) * self.wave_gain
        current_level = max(0.0, min(1.0, current_level))  # 限制在0-1之间
        
        # 基础波形高度 - 增加基础高度
        base_heights = [4, 8, 6, 12, 8, 10, 4]  # 基础高度翻倍
        
        # 如果有音频信号，使用实时数据；否则使用低强度动画
        if current_level > 0.01:  # 有声音输入
            for i, base_height in enumerate(base_heights):
                # 使用真实音频电平 + 轻微的频率差异
                freq_variation = 1.0 + (i - 3) * 0.15  # 增加频率差异
                level_variation = current_level * freq_variation
                level_variation = max(0.2, min(1.0, level_variation))  # 最小高度20%
                
                # 添加轻微的时间延迟模拟频谱
                time_offset = self._anim_phase * 0.1 + i * 0.2
                smooth_factor = 0.8 + 0.2 * math.sin(time_offset)
                
                final_height = base_height * level_variation * smooth_factor
                bar_height = int(final_height)
                
                x = wave_x + i * 3
                y_top = center_y - bar_height // 2
                y_bottom = center_y + bar_height // 2
                c.create_rectangle(x, y_top, x + 2, y_bottom,
                                 fill=wave_color, outline='')
        else:
            # 静音时显示低强度的待机动画
            for i, base_height in enumerate(base_heights):
                time_factor = (self._anim_phase * 0.1 + i * 0.5)
                idle_amplitude = 0.3 + 0.2 * math.sin(time_factor)  # 增加待机波动
                
                final_height = base_height * idle_amplitude
                bar_height = int(final_height)
                
                x = wave_x + i * 3
                y_top = center_y - bar_height // 2
                y_bottom = center_y + bar_height // 2
                c.create_rectangle(x, y_top, x + 2, y_bottom,
                                 fill=wave_color, outline='')
        
        # 录音指示点 - 更自然的脉动
        import math
        dot_time = self._anim_phase * 0.3  # 慢一点的脉动
        dot_alpha = (math.sin(dot_time) + 1) / 2  # 0-1之间的平滑脉动
        
        # 颜色插值：白色到淡红色
        if dot_alpha > 0.7:
            dot_color = '#ffffff'  # 白色
        elif dot_alpha > 0.3:
            dot_color = '#ffe6e6'  # 淡粉色
        else:
            dot_color = '#fca5a5'  # 淡红色
        
        # 大小脉动
        dot_size = int(2 + 2 * dot_alpha)  # 2-4之间变化
        dot_x = w - 12
        
        c.create_oval(dot_x - dot_size, center_y - dot_size, 
                     dot_x + dot_size, center_y + dot_size, 
                     fill=dot_color, outline='')
    
    def _toggle_recording(self):
        """切换录音状态"""
        if not self.is_recording:
            # 开始录音
            self.is_recording = True
            # 录音时置顶窗口
            if self.window and self.mode == "status":
                try:
                    self.window.lift()
                    self.window.attributes('-topmost', True)
                    logger.debug("录音时重新置顶图标窗口")
                except Exception as e:
                    logger.warning(f"置顶窗口失败: {e}")
            
            if getattr(self, 'record_button', None):
                self.record_button.configure(
                    text="⏹️ 停止",
                    bg='#e74c3c'
                )
            
            # 确保文本输入框获得焦点
            if getattr(self, 'text_widget', None):
                self.text_widget.focus_set()
            if getattr(self, 'icon_canvas', None):
                logger.info("切换到录音状态，启动动画")
                self._start_recording_anim()
            else:
                logger.warning("icon_canvas 不存在，无法启动动画")
            if getattr(self, 'status_label', None):
                self.status_label.configure(text="🎤 正在录音...")
            self.on_record_start()
            logger.info("悬浮窗：开始录音")
        else:
            # 停止录音 - 立即更新状态
            self.is_recording = False
            if getattr(self, 'icon_canvas', None) and getattr(self, '_anim_job', None):
                self.window.after_cancel(self._anim_job)
                self._anim_job = None
            
            # 立即绘制静止图标
            if getattr(self, 'icon_canvas', None):
                self._draw_idle_icon()
                
            # 更新其他UI元素
            if getattr(self, 'record_button', None):
                self.record_button.configure(
                    text="🎤 录音",
                    bg='#3498db'
                )
            if getattr(self, 'status_label', None):
                self.status_label.configure(text="准备就绪")
            
            logger.info("悬浮窗：停止录音")
            
            # 最后调用停止回调，避免回调中的状态更新覆盖我们的UI状态
            self.on_record_stop()
    
    def _toggle_translation(self):
        """切换翻译录音状态"""
        if not self.is_translating:
            # 开始翻译录音
            self.is_translating = True
            self.translate_button.configure(
                text="⏹️ 停止",
                bg='#e74c3c'
            )
            self.status_label.configure(text="🎤 正在录音 (翻译模式)")
            self.on_translate_start()
            logger.info("悬浮窗：开始翻译录音")
        else:
            # 停止翻译录音
            self.is_translating = False
            self.translate_button.configure(
                text="🌐 翻译",
                bg='#e74c3c'
            )
            self.status_label.configure(text="🔄 正在翻译...")
            self.on_translate_stop()
            logger.info("悬浮窗：停止翻译录音")
    
    def update_status(self, status_text):
        """更新状态文本"""
        if self.status_label:
            self.status_label.configure(text=status_text)
        # status 模式不需要复杂的计时器逻辑
        if self.mode != "status":
            # 录音计时器控制
            if isinstance(status_text, str) and status_text.startswith("🎤 "):
                self._start_timer()
            elif status_text.startswith("🔄 ") or status_text.startswith("✅ ") or status_text.startswith("❌ "):
                self._stop_timer()

    def set_text(self, text: str):
        """设置显示文本：status 模式写入只读显示框；full 模式写入可编辑框"""
        if getattr(self, 'display_widget', None) is not None:
            self.display_widget.configure(state=tk.NORMAL)
            self.display_widget.delete('1.0', tk.END)
            if text:
                self.display_widget.insert(tk.END, text)
            self.display_widget.configure(state=tk.DISABLED)
        elif getattr(self, 'text_widget', None) is not None:
            self.text_widget.delete('1.0', tk.END)
            if text:
                self.text_widget.insert(tk.END, text)
            # 确保文本输入框获得焦点
            try:
                self.text_widget.focus_set()
            except Exception:
                pass

    # --- 计时与电平显示 ---
    def _start_timer(self):
        if getattr(self, '_timer_running', False):
            return
        self._timer_running = True
        self._start_time = time.time()
        self._tick_timer()

    def _stop_timer(self):
        self._timer_running = False

    def _tick_timer(self):
        if not getattr(self, '_timer_running', False):
            return
        try:
            elapsed = int(time.time() - getattr(self, '_start_time', time.time()))
            mm = elapsed // 60
            ss = elapsed % 60
            if getattr(self, 'time_label', None) is not None:
                self.time_label.configure(text=f"{mm:02d}:{ss:02d}")
            # 绘制简单电平条
            if getattr(self, 'level_canvas', None) is not None:
                w = self.level_canvas.winfo_width() or 260
                h = self.level_canvas.winfo_height() or 28
                self.level_canvas.delete("all")
                pad_l, pad_r, pad_t, pad_b = 8, 8, 4, 4
                mid = h // 2
                base_y = mid
                # 顶部绿色电平条（瞬时电平，宽度按 _level 比例）更醒目
                avail_w = (w - pad_l - pad_r)
                level_scaled = max(0.0, min(1.0, float(self._level) * float(self.wave_gain)))
                level_w = max(1, int(avail_w * level_scaled))
                self.level_canvas.create_rectangle(
                    pad_l, pad_t + 4, pad_l + level_w, pad_t + 10,
                    fill="#2ecc71", width=0)

                # 虚线基线
                self.level_canvas.create_line(
                    pad_l, base_y, w - pad_r, base_y,
                    fill="#7f8c8d", dash=(3, 3))
                # 中间竖线（光标）
                playhead_x = pad_l + 48
                self.level_canvas.create_line(
                    playhead_x, pad_t, playhead_x, h - pad_b,
                    fill="#ecf0f1", width=2)

                # 右侧柱状波形（滚动效果：右侧最新，左侧较旧）
                if self._wave_samples:
                    right_w = max(0, (w - pad_r) - playhead_x)
                    bar_step = 4
                    bar_width = 3
                    num_bars = max(1, right_w // bar_step)
                    samples = self._wave_samples
                    chunk = 64  # 每根柱使用的样本窗口，越小越灵敏
                    values = []
                    tail = len(samples)
                    for _ in range(num_bars):
                        start = max(0, tail - chunk)
                        seg = samples[start:tail]
                        if seg:
                            sq = [float(s) * float(s) for s in seg]
                            rms = (sum(sq) / len(sq)) ** 0.5
                        else:
                            rms = 0.0
                        # 应用增益并压限
                        rms = max(0.0, min(1.0, rms * float(self.wave_gain)))
                        values.append(rms)
                        tail = start
                        if tail <= 0:
                            break
                    # 反转，使得左旧右新
                    values = list(reversed(values))
                    x = playhead_x
                    for rms in values:
                        bar_h = int(rms * (h / 2 - 4))
                        if bar_h > 0:
                            self.level_canvas.create_line(
                                x, base_y - bar_h,
                                x, base_y + bar_h,
                                fill="#ecf0f1", width=bar_width)
                        x += bar_step
        except Exception:
            pass
        # 100ms 刷新
        self.window.after(100, self._tick_timer)

    def set_level(self, level: float):
        self._level = level

    def push_wave_samples(self, samples):
        """推入一段实时样本（np.ndarray 或 list[float]，范围约 [-1,1]）。"""
        try:
            if not isinstance(samples, (list, tuple)):
                # numpy 数组
                samples = samples.tolist()
            # 追加并裁剪容量
            self._wave_samples.extend(samples)
            if len(self._wave_samples) > self._wave_capacity:
                self._wave_samples = self._wave_samples[-self._wave_capacity:]
        except Exception:
            pass

    def reset_wave(self):
        """清空波形缓存（开始录音前调用）。"""
        try:
            self._wave_samples = []
        except Exception:
            pass

    def get_text(self) -> str:
        if getattr(self, 'text_widget', None) is not None:
            return self.text_widget.get('1.0', tk.END).rstrip('\n')
        return ""
    
    def reset_state(self):
        """重置状态"""
        self.is_recording = False
        self.is_translating = False
        
        if self.record_button:
            self.record_button.configure(
                text="🎤 录音",
                bg='#3498db'
            )
        
        if getattr(self, 'icon_canvas', None):
            # 停止动画并绘制静止图标
            if getattr(self, '_anim_job', None):
                self.window.after_cancel(self._anim_job)
                self._anim_job = None
            self._draw_idle_icon()
        
        if self.translate_button:
            self.translate_button.configure(
                text="🌐 翻译",
                bg='#e74c3c'
            )
        
        if self.status_label:
            self.status_label.configure(text="准备就绪")
    
    def show(self):
        """显示悬浮窗"""
        if self.window:
            self.window.deiconify()
            self.is_visible = True
            self.follow_mouse = False  # 不跟随鼠标移动
    
    def hide(self):
        """隐藏悬浮窗（status模式不隐藏）"""
        if self.mode != "status":
            self._hide_window()
        else:
            logger.debug("status模式下忽略隐藏请求")
    
    def run(self):
        """运行悬浮窗"""
        if self.window:
            self.window.mainloop()
    
    def destroy(self):
        """销毁悬浮窗"""
        if self.window:
            self.window.destroy()
            self.window = None

    # --- 内部操作 ---
    def _optimize_text(self):
        """调用外部优化回调，使用 LLM 对文本进行优化，不阻塞 UI"""
        if not callable(self.on_optimize):
            self.update_status("⚠️ 未配置优化功能")
            return
        current_text = self.get_text()
        if not current_text.strip():
            return
        self.update_status("✨ 正在优化...")

        def _task():
            try:
                optimized = self.on_optimize(current_text)
                def _apply():
                    self.set_text(optimized or current_text)
                    self.update_status("✅ 优化完成")
                self.window.after(0, _apply)
            except Exception as e:
                def _err():
                    self.update_status(f"❌ 优化失败: {e}")
                self.window.after(0, _err)
        import threading
        threading.Thread(target=_task, daemon=True).start()

    def _write_text(self):
        """调用外部写入回调，将文本写入目标窗口"""
        if not callable(self.on_write):
            self.update_status("⚠️ 未配置写入功能")
            return
        text_to_write = self.get_text()
        if not text_to_write.strip():
            return
        self.update_status("✍️ 正在写入...")

        def _task():
            try:
                self.on_write(text_to_write, self.target_window_handle)
                def _ok():
                    self.update_status("✅ 写入完成")
                self.window.after(0, _ok)
            except Exception as e:
                def _err():
                    self.update_status(f"❌ 写入失败: {e}")
                self.window.after(0, _err)
        import threading
        threading.Thread(target=_task, daemon=True).start()
