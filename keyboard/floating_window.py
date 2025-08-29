import tkinter as tk
from tkinter import ttk
import threading
import time
from pynput import mouse
import os

# Placeholder logger since we're not importing the original utils module
class logger:
    @staticmethod
    def info(msg): print(f"INFO: {msg}")
    @staticmethod
    def warning(msg): print(f"WARNING: {msg}")
    @staticmethod
    def error(msg): print(f"ERROR: {msg}")
    @staticmethod
    def debug(msg): print(f"DEBUG: {msg}")


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
        self.is_processing = False  # 录音完成后到转录开始之间的状态
        self.is_translating = False
        self.is_visible = False
        self.follow_mouse = True
        self.target_window_handle = None  # 记录呼出时鼠标所在窗口句柄（Windows）
        
        # 鼠标位置
        self.mouse_x = 0
        self.mouse_y = 0
        
        # 初始化图像引用变量，防止垃圾回收
        self.idle_icon_image = None
        self.recording_icon_image = None
        self.processing_icon_image = None
        
        # 初始化动画和波形相关变量
        self._anim_phase = 0
        self._anim_job = None
        self._wave_samples = []
        self._image_cache = {}
        self._last_wave_hash = None
        
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
                # 如果没有焦点，尝试设置焦点到文本框
                if hasattr(self, 'text_widget') and self.text_widget:
                    self.text_widget.focus_set()
                    logger.info("已重新设置焦点到文本框")
        except Exception as e:
            logger.error(f"获取窗口状态失败: {e}")

    def _create_window(self):
        """创建悬浮窗"""
        self.window = tk.Tk()
        self.window.title("语音输入")
        # 统一管理窗口尺寸，供显示时使用
        if self.mode == "status":
            self.window_width = 100   # 圆形按钮尺寸
            self.window_height = 100
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
        
        # 创建主框架 - 减少边距确保完全居中
        main_frame = tk.Frame(self.window, bg=self.transparent_color, padx=5, pady=5)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        if self.mode == "status":
            # 圆形按钮模式 - 高清画布
            self.icon_canvas = tk.Canvas(
                main_frame, width=80, height=80,
                bg=self.transparent_color, highlightthickness=0, cursor='hand2',
                bd=0, relief='flat'
            )
            self.icon_canvas.pack(expand=True)
            self.icon_canvas.bind("<Button-1>", lambda e: self._toggle_recording())
            self.icon_canvas.bind("<Enter>", self._on_icon_hover)
            self.icon_canvas.bind("<Leave>", self._on_icon_leave)

            # 动画和悬浮状态
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
        
        def on_click(x, y, button, pressed):
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
            self.target_window_handle = None
    
    def _hide_window(self):
        """隐藏悬浮窗（status模式不隐藏）"""
        if self.window and self.mode != "status":
            self.window.withdraw()
            self.is_visible = False
            self.follow_mouse = False
        elif self.mode == "status":
            logger.debug("status模式下不隐藏常驻图标")
    
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
        if not self.is_recording and not self.is_processing:  # 只在非录音和非处理状态显示悬浮提示
            self._show_hover_text()
        
    def _on_icon_leave(self, event):
        """鼠标离开图标"""
        self._is_hovering = False
        if self._hover_text_job:
            self.window.after_cancel(self._hover_text_job)
            self._hover_text_job = None
        if not self.is_recording and not self.is_processing:
            self._draw_idle_icon()
        elif self.is_processing:
            self._draw_processing_icon()
    
    def _show_hover_text(self):
        """显示悬浮提示文本 - 保持圆形按钮，添加浮动提示"""
        if not self._is_hovering or self.is_recording or self.is_processing:
            return
        
        c = getattr(self, 'icon_canvas', None)
        if not c:
            return
        
        # 不改变画布尺寸，在原有80x80的画布上绘制
        c.delete("all")
        size = 80
        center = size // 2
        
        # 检查缓存
        cache_key = "hover_text"
        if cache_key in self._image_cache:
            cached_image = self._image_cache[cache_key]
            c.create_image(center, center, image=cached_image)
            return
        
        # 先绘制原始的圆形按钮（稍微透明一点）
        try:
            from PIL import Image, ImageDraw, ImageTk, ImageFilter, ImageFont
            
            scale = 16
            img_size = size * scale
            img = Image.new('RGBA', (img_size, img_size), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            
            # 绘制半透明的原始按钮作为背景
            cx, cy = img_size // 2, img_size // 2
            radius = (img_size - 40 * scale) // 2
            
            # 悬停状态的颜色 - 稍微亮一点
            hover_color = (74, 85, 104, 200)  # 半透明的蓝灰色
            border_color = (156, 163, 175, 150)  # 半透明边框
            
            # 主按钮
            draw.ellipse(
                [cx - radius, cy - radius, cx + radius, cy + radius],
                fill=hover_color
            )
            
            # 边框
            border_width = 3 * scale
            draw.ellipse(
                [cx - radius, cy - radius, cx + radius, cy + radius],
                outline=border_color, width=border_width
            )
            
            # 绘制提示图标（简化的麦克风 + 文字）
            icon_color = (226, 232, 240, 255)  # 白色图标
            
            # 麦克风图标（更小一点）
            mic_w, mic_h = 6 * scale, 12 * scale
            mic_x1, mic_y1 = cx - mic_w//2, cy - mic_h//2 - 4*scale
            mic_x2, mic_y2 = cx + mic_w//2, cy + mic_h//2 - 4*scale
            
            # 绘制圆角矩形麦克风
            corner_radius = 3 * scale
            try:
                draw.rounded_rectangle(
                    [mic_x1, mic_y1, mic_x2, mic_y2],
                    radius=corner_radius, fill=icon_color
                )
            except AttributeError:
                draw.ellipse([mic_x1, mic_y1, mic_x2, mic_y2], fill=icon_color)
            
            # 支架
            stand_w = 2 * scale
            stand_h = 6 * scale
            stand_x1 = cx - stand_w//2
            stand_y1 = cy + mic_h//2 - 4*scale
            draw.rectangle([stand_x1, stand_y1, stand_x1 + stand_w, stand_y1 + stand_h], fill=icon_color)
            
            # 底座
            base_w = 8 * scale
            base_h = 2 * scale
            base_x1 = cx - base_w//2
            base_y1 = stand_y1 + stand_h
            draw.rectangle([base_x1, base_y1, base_x1 + base_w, base_y1 + base_h], fill=icon_color)
            
            # 添加文字提示 "CLICK" 在按钮下方
            try:
                font = ImageFont.truetype("arial.ttf", int(8 * scale))
            except:
                try:
                    font = ImageFont.load_default()
                except:
                    font = None
            
            text = "CLICK"
            if font:
                try:
                    bbox = draw.textbbox((0, 0), text, font=font)
                    text_w = bbox[2] - bbox[0]
                    text_x = cx - text_w // 2
                    text_y = cy + radius // 2 + 3 * scale
                    draw.text((text_x, text_y), text, fill=icon_color, font=font)
                except:
                    # 如果字体绘制失败，跳过文字
                    pass
            
            # 多级缩放抗锯齿
            img_8x = img.resize((size * 8, size * 8), Image.Resampling.LANCZOS)
            img_4x = img_8x.resize((size * 4, size * 4), Image.Resampling.LANCZOS)
            img_2x = img_4x.resize((size * 2, size * 2), Image.Resampling.LANCZOS)
            img_final = img_2x.resize((size, size), Image.Resampling.LANCZOS)
            
            img_final = img_final.filter(ImageFilter.GaussianBlur(radius=0.2))
            
            # 创建PhotoImage并缓存
            photo_image = ImageTk.PhotoImage(img_final)
            self._image_cache[cache_key] = photo_image
            c.create_image(center, center, image=photo_image)
            
        except ImportError:
            # 简化回退版本
            radius = size // 2 - 4
            hover_color = '#4a5568'
            
            # 悬停状态的圆形按钮
            c.create_oval(
                center - radius, center - radius,
                center + radius, center + radius,
                fill=hover_color, outline='#9ca3af', width=2
            )
            
            # 简化的麦克风图标
            mic_size = 8
            c.create_oval(
                center - mic_size//2, center - mic_size//2 - 2,
                center + mic_size//2, center + mic_size//2 - 2,
                fill='#e2e8f0', outline=''
            )
            c.create_rectangle(
                center - 1, center + mic_size//2 - 2,
                center + 1, center + mic_size//2 + 2,
                fill='#e2e8f0', outline=''
            )
            
            # 提示文字
            c.create_text(center, center + radius - 8, text="CLICK", 
                         fill='#e2e8f0', font=('Arial', 7), anchor='center')
        
        # 定时恢复
        self._hover_text_job = self.window.after(2000, self._restore_from_hover)
    
    def _restore_from_hover(self):
        """从悬停状态恢复到正常状态"""
        if not self.is_recording and not self.is_processing:
            self._draw_idle_icon()

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
                            elif self.is_processing:
                                self._draw_processing_icon()
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
        """绘制静止状态的完美圆形按钮 - 超高清抗锯齿"""
        c = getattr(self, 'icon_canvas', None)
        if not c:
            logger.warning("icon_canvas 不存在")
            return
        
        try:
            c.delete("all")
            # 使用正方形的画布来绘制完美圆形
            size = 80  # 圆形按钮的直径
            center = size // 2
            
            # 更新画布尺寸为正方形
            c.config(width=size, height=size)
            
            # 如果有自定义图标，优先使用
            if self.custom_icon_image:
                c.create_image(center, center, image=self.custom_icon_image)
                logger.debug("使用自定义图标绘制完成")
                return
            
            # 使用PIL创建完美的圆形按钮
            try:
                from PIL import Image, ImageDraw, ImageTk, ImageFilter
                import numpy as np
                
                # 使用16倍分辨率进行超高清抗锯齿
                scale = 16
                img_size = size * scale
                
                # 创建超高分辨率的RGBA图像
                img = Image.new('RGBA', (img_size, img_size), (0, 0, 0, 0))
                draw = ImageDraw.Draw(img)
                
                # 按钮样式：现代化的深色圆形
                button_color = (45, 55, 72, 255)  # 深蓝灰色 #2d3748
                border_color = (113, 128, 150, 60)  # 半透明边框 #718096
                shadow_color = (0, 0, 0, 30)  # 阴影
                
                # 计算圆形参数
                radius = (img_size - 40 * scale) // 2  # 留出边距
                cx, cy = img_size // 2, img_size // 2
                
                # 绘制阴影（稍微偏移）
                shadow_offset = 4 * scale
                draw.ellipse(
                    [cx - radius + shadow_offset, cy - radius + shadow_offset, 
                     cx + radius + shadow_offset, cy + radius + shadow_offset],
                    fill=shadow_color
                )
                
                # 绘制主要的圆形按钮
                draw.ellipse(
                    [cx - radius, cy - radius, cx + radius, cy + radius],
                    fill=button_color
                )
                
                # 绘制边框
                border_width = 2 * scale
                draw.ellipse(
                    [cx - radius, cy - radius, cx + radius, cy + radius],
                    outline=border_color, width=border_width
                )
                
                # 绘制精美的麦克风图标
                self._draw_microphone_icon(draw, cx, cy, scale)
                
                # 多级缩放实现完美抗锯齿
                # 16x -> 8x -> 4x -> 2x -> 1x
                img_8x = img.resize((size * 8, size * 8), Image.Resampling.LANCZOS)
                img_4x = img_8x.resize((size * 4, size * 4), Image.Resampling.LANCZOS)
                img_2x = img_4x.resize((size * 2, size * 2), Image.Resampling.LANCZOS)
                img_final = img_2x.resize((size, size), Image.Resampling.LANCZOS)
                
                # 应用轻微的高斯模糊以获得更平滑的边缘
                img_final = img_final.filter(ImageFilter.GaussianBlur(radius=0.2))
                
                # 创建PhotoImage并保存引用以防止垃圾回收
                self.idle_icon_image = ImageTk.PhotoImage(img_final)
                c.create_image(center, center, image=self.idle_icon_image)
                
                logger.debug("使用PIL绘制完美圆形按钮完成")
                return
                
            except ImportError:
                logger.warning("PIL不可用，使用Tkinter绘制")
            except Exception as e:
                logger.warning(f"PIL绘制静止图标失败: {e}，回退到Tkinter绘制")
            
            # 回退到Tkinter圆形绘制
            self._draw_idle_icon_tkinter_circle(size, center)
            
        except Exception as e:
            logger.error(f"绘制静止图标失败: {e}")
    
    def _draw_microphone_icon(self, draw, cx, cy, scale):
        """绘制精美的麦克风图标"""
        icon_color = (226, 232, 240, 255)  # 浅灰色 #e2e8f0
        
        # 麦克风主体 - 圆角矩形
        mic_w, mic_h = 8 * scale, 16 * scale
        mic_x1, mic_y1 = cx - mic_w//2, cy - mic_h//2 - 2*scale
        mic_x2, mic_y2 = cx + mic_w//2, cy + mic_h//2 - 2*scale
        
        # 绘制圆角矩形作为麦克风主体
        corner_radius = 4 * scale
        try:
            draw.rounded_rectangle(
                [mic_x1, mic_y1, mic_x2, mic_y2],
                radius=corner_radius, fill=icon_color
            )
        except AttributeError:
            # 回退到椭圆形麦克风
            draw.ellipse([mic_x1, mic_y1, mic_x2, mic_y2], fill=icon_color)
        
        # 麦克风支架
        stand_w, stand_h = 2 * scale, 8 * scale
        stand_x1, stand_y1 = cx - stand_w//2, cy + mic_h//2 - 2*scale
        stand_x2, stand_y2 = cx + stand_w//2, cy + mic_h//2 - 2*scale + stand_h
        draw.rectangle([stand_x1, stand_y1, stand_x2, stand_y2], fill=icon_color)
        
        # 麦克风底座（小的横线）
        base_w = 12 * scale
        base_h = 2 * scale
        base_x1, base_y1 = cx - base_w//2, stand_y2
        base_x2, base_y2 = cx + base_w//2, stand_y2 + base_h
        draw.rectangle([base_x1, base_y1, base_x2, base_y2], fill=icon_color)
        
        # 声音传播线条（装饰性）
        for i in range(2):
            offset = (i + 1) * 6 * scale
            line_length = 4 * scale
            # 右侧弧线
            arc_x = cx + mic_w//2 + offset
            arc_y = cy - 2*scale
            draw.arc(
                [arc_x - line_length, arc_y - line_length, 
                 arc_x + line_length, arc_y + line_length],
                start=-30, end=30, fill=icon_color, width=2*scale
            )
    
    def _draw_idle_icon_tkinter_circle(self, size, center):
        """使用Tkinter绘制圆形按钮（回退方法）"""
        c = self.icon_canvas
        
        # 圆形按钮参数
        radius = size // 2 - 4
        button_color = '#2d3748'
        border_color = '#718096'
        icon_color = '#e2e8f0'
        
        # 绘制圆形背景
        c.create_oval(
            center - radius, center - radius,
            center + radius, center + radius,
            fill=button_color, outline=border_color, width=2
        )
        
        # 绘制简单的麦克风图标
        mic_size = 12
        # 麦克风主体
        c.create_oval(
            center - mic_size//2, center - mic_size//2 - 4,
            center + mic_size//2, center + mic_size//2 - 4,
            fill=icon_color, outline=''
        )
        # 支架
        c.create_rectangle(
            center - 1, center + mic_size//2 - 4,
            center + 1, center + mic_size//2 + 4,
            fill=icon_color, outline=''
        )
        # 底座
        c.create_rectangle(
            center - 6, center + mic_size//2 + 4,
            center + 6, center + mic_size//2 + 6,
            fill=icon_color, outline=''
        )
    
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

    def _draw_processing_icon(self):
        """绘制处理状态的圆形按钮 - 优雅的处理动画"""
        c = getattr(self, 'icon_canvas', None)
        if not c:
            return
        
        try:
            c.delete("all")
            size = 80
            center = size // 2
            
            # 使用PIL创建处理状态的圆形按钮
            try:
                from PIL import Image, ImageDraw, ImageTk, ImageFilter
                import math
                
                scale = 16
                img_size = size * scale
                img = Image.new('RGBA', (img_size, img_size), (0, 0, 0, 0))
                draw = ImageDraw.Draw(img)
                
                # 处理状态的橙色按钮
                button_color = (249, 115, 22, 255)  # 橙色 #f97316
                accent_color = (251, 146, 60, 255)  # 亮橙色
                
                cx, cy = img_size // 2, img_size // 2
                radius = (img_size - 40 * scale) // 2
                
                # 主按钮
                draw.ellipse(
                    [cx - radius, cy - radius, cx + radius, cy + radius],
                    fill=button_color
                )
                
                # 绘制旋转的处理指示器
                self._draw_processing_spinner(draw, cx, cy, radius, scale)
                
                # 多级缩放抗锯齿
                img_8x = img.resize((size * 8, size * 8), Image.Resampling.LANCZOS)
                img_4x = img_8x.resize((size * 4, size * 4), Image.Resampling.LANCZOS)
                img_2x = img_4x.resize((size * 2, size * 2), Image.Resampling.LANCZOS)
                img_final = img_2x.resize((size, size), Image.Resampling.LANCZOS)
                
                img_final = img_final.filter(ImageFilter.GaussianBlur(radius=0.2))
                
                # 创建PhotoImage并保存引用以防止垃圾回收
                self.processing_icon_image = ImageTk.PhotoImage(img_final)
                c.create_image(center, center, image=self.processing_icon_image)
                
                return
                
            except ImportError:
                logger.warning("PIL不可用，使用简化的处理图标")
            except Exception as e:
                logger.warning(f"PIL绘制处理图标失败: {e}，回退到简化版本")
            
            # 回退到简化版本
            self._draw_processing_icon_simple(size, center)
            
        except Exception as e:
            logger.error(f"绘制处理图标失败: {e}")
    
    def _draw_processing_spinner(self, draw, cx, cy, radius, scale):
        """绘制旋转的处理指示器"""
        import math
        
        # 计算旋转角度
        rotation = (getattr(self, '_anim_phase', 0) * 0.2) % (2 * math.pi)
        
        # 绘制多个旋转的弧形
        arc_color = (255, 255, 255, 200)  # 白色，半透明
        arc_radius = radius * 0.6
        arc_width = 4 * scale
        
        # 绘制3个等间距的弧形，形成旋转效果
        for i in range(3):
            start_angle = rotation + i * (2 * math.pi / 3)
            arc_length = math.pi / 3  # 60度弧长
            
            # 计算弧形的起始和结束角度（转换为度数）
            start_deg = math.degrees(start_angle)
            end_deg = math.degrees(start_angle + arc_length)
            
            # 绘制弧形
            arc_box = [
                cx - arc_radius, cy - arc_radius,
                cx + arc_radius, cy + arc_radius
            ]
            
            # PIL的arc方法需要角度，并且起始角度从3点钟位置开始
            draw.arc(arc_box, start=start_deg - 90, end=end_deg - 90, 
                    fill=arc_color, width=arc_width)
        
        # 中心的处理图标（齿轮或点）
        center_color = (255, 255, 255, 255)
        dot_radius = 3 * scale
        
        # 绘制中心点
        draw.ellipse(
            [cx - dot_radius, cy - dot_radius, 
             cx + dot_radius, cy + dot_radius],
            fill=center_color
        )
    
    def _draw_processing_icon_simple(self, size, center):
        """简化的处理图标（回退方法）"""
        c = self.icon_canvas
        
        radius = size // 2 - 4
        button_color = '#f97316'  # 橙色
        
        # 主按钮
        c.create_oval(
            center - radius, center - radius,
            center + radius, center + radius,
            fill=button_color, outline=''
        )
        
        # 简单的旋转点
        import math
        rotation = (getattr(self, '_anim_phase', 0) * 0.3) % (2 * math.pi)
        
        dot_color = 'white'
        dot_radius = 3
        orbit_radius = radius * 0.4
        
        for i in range(3):
            angle = rotation + i * (2 * math.pi / 3)
            dot_x = center + int(math.cos(angle) * orbit_radius)
            dot_y = center + int(math.sin(angle) * orbit_radius)
            
            c.create_oval(
                dot_x - dot_radius, dot_y - dot_radius,
                dot_x + dot_radius, dot_y + dot_radius,
                fill=dot_color, outline=''
            )

    def _draw_recording_icon(self):
        """绘制录音状态的圆形按钮 - 真实声纹波形"""
        c = getattr(self, 'icon_canvas', None)
        if not c:
            return
            
        try:
            c.delete("all")
            size = 80
            center = size // 2
            
            # 创建缓存键，包含动画相位和波形数据的哈希
            wave_hash = hash(tuple(self._wave_samples[-20:]) if self._wave_samples else 0)
            cache_key = f"recording_{self._anim_phase % 20}_{wave_hash}"  # 减少缓存键数量
            
            # 检查缓存
            if cache_key in self._image_cache:
                cached_image = self._image_cache[cache_key]
                c.create_image(center, center, image=cached_image)
                return
            
            # 使用PIL创建录音状态的圆形按钮
            try:
                from PIL import Image, ImageDraw, ImageTk, ImageFilter
                import numpy as np
                
                scale = 16
                img_size = size * scale
                img = Image.new('RGBA', (img_size, img_size), (0, 0, 0, 0))
                draw = ImageDraw.Draw(img)
                
                # 录音状态的红色按钮
                button_color = (220, 38, 38, 255)  # 红色 #dc2626
                pulse_color = (239, 68, 68, 100)  # 半透明的脉冲效果
                
                cx, cy = img_size // 2, img_size // 2
                base_radius = (img_size - 40 * scale) // 2
                
                # 绘制脉冲效果（呼吸动画）
                import math
                pulse_factor = 0.8 + 0.2 * math.sin(self._anim_phase * 0.3)
                pulse_radius = int(base_radius * (1 + 0.3 * pulse_factor))
                
                # 外层脉冲圆环
                draw.ellipse(
                    [cx - pulse_radius, cy - pulse_radius, 
                     cx + pulse_radius, cy + pulse_radius],
                    fill=pulse_color
                )
                
                # 主按钮
                draw.ellipse(
                    [cx - base_radius, cy - base_radius, 
                     cx + base_radius, cy + base_radius],
                    fill=button_color
                )
                
                # 在按钮内部绘制真实声纹波形
                self._draw_realtime_waveform(draw, cx, cy, base_radius, scale)
                
                # 多级缩放抗锯齿
                img_8x = img.resize((size * 8, size * 8), Image.Resampling.LANCZOS)
                img_4x = img_8x.resize((size * 4, size * 4), Image.Resampling.LANCZOS)
                img_2x = img_4x.resize((size * 2, size * 2), Image.Resampling.LANCZOS)
                img_final = img_2x.resize((size, size), Image.Resampling.LANCZOS)
                
                img_final = img_final.filter(ImageFilter.GaussianBlur(radius=0.2))
                
                # 创建PhotoImage并缓存，同时保存当前引用防止垃圾回收
                photo_image = ImageTk.PhotoImage(img_final)
                
                # 限制缓存大小，清理老的缓存项
                if len(self._image_cache) > 50:
                    # 清理一半的缓存
                    keys_to_remove = list(self._image_cache.keys())[:25]
                    for key in keys_to_remove:
                        del self._image_cache[key]
                
                # 缓存图像并保存当前录音图标引用
                self._image_cache[cache_key] = photo_image
                self.recording_icon_image = photo_image  # 保存当前引用防止垃圾回收
                c.create_image(center, center, image=photo_image)
                
                return
                
            except ImportError:
                logger.warning("PIL不可用，使用简化的录音图标")
            except Exception as e:
                logger.warning(f"PIL绘制录音图标失败: {e}，回退到简化版本")
            
            # 回退到简化版本
            self._draw_recording_icon_simple(size, center)
            
        except Exception as e:
            logger.error(f"绘制录音图标失败: {e}")
    
    def _draw_realtime_waveform(self, draw, cx, cy, radius, scale):
        """绘制真实的声纹波形"""
        waveform_color = (255, 255, 255, 255)  # 白色波形
        
        # 获取真实的音频样本数据
        samples = getattr(self, '_wave_samples', [])
        if not samples:
            # 如果没有真实数据，生成一些动态的模拟波形
            import math
            samples = []
            for i in range(64):
                # 创建复杂的合成波形
                t = (self._anim_phase + i) * 0.1
                wave1 = math.sin(t) * 0.3
                wave2 = math.sin(t * 2.3 + 0.5) * 0.2
                wave3 = math.sin(t * 4.7 + 1.2) * 0.1
                sample = wave1 + wave2 + wave3
                samples.append(sample)
        
        # 限制样本数量，只显示最新的64个样本
        display_samples = samples[-64:] if len(samples) > 64 else samples
        if len(display_samples) < 64:
            # 填充到64个样本
            display_samples = [0.0] * (64 - len(display_samples)) + display_samples
        
        # 计算波形绘制区域
        waveform_width = int(radius * 1.2)  # 波形宽度
        waveform_height = int(radius * 0.8)  # 波形高度
        
        # 绘制波形（从圆心向外辐射的方式）
        num_bars = 32  # 减少条数，看起来更清晰
        bar_width = max(1 * scale, waveform_width * 2 // num_bars)
        
        for i in range(num_bars):
            # 计算每个条的位置（圆形分布）
            angle = (i / num_bars) * 2 * math.pi - math.pi / 2  # 从顶部开始
            
            # 获取对应的音频样本
            sample_index = int(i * len(display_samples) / num_bars)
            if sample_index < len(display_samples):
                amplitude = abs(display_samples[sample_index])
            else:
                amplitude = 0.0
            
            # 增强波形显示效果
            amplitude = min(1.0, amplitude * self.wave_gain)  # 应用增益
            
            # 计算条的长度（从中心向外）
            min_length = radius // 4  # 最小长度
            max_length = radius * 0.7  # 最大长度
            bar_length = int(min_length + amplitude * (max_length - min_length))
            
            # 计算条的起始和结束位置
            start_x = cx + int(math.cos(angle) * min_length)
            start_y = cy + int(math.sin(angle) * min_length)
            end_x = cx + int(math.cos(angle) * bar_length)
            end_y = cy + int(math.sin(angle) * bar_length)
            
            # 根据振幅调整颜色强度
            alpha = int(100 + 155 * amplitude)  # 动态透明度
            color = (255, 255, 255, alpha)
            
            # 绘制波形条（使用粗线）
            line_width = max(2 * scale, bar_width)
            draw.line([start_x, start_y, end_x, end_y], 
                     fill=color, width=line_width)
    
    def _draw_recording_icon_simple(self, size, center):
        """简化的录音图标（回退方法）"""
        c = self.icon_canvas
        
        radius = size // 2 - 4
        button_color = '#dc2626'  # 红色
        
        # 脉冲效果
        import math
        pulse_factor = 0.8 + 0.2 * math.sin(getattr(self, '_anim_phase', 0) * 0.3)
        pulse_radius = int(radius * (1 + 0.2 * pulse_factor))
        
        # 外层脉冲
        c.create_oval(
            center - pulse_radius, center - pulse_radius,
            center + pulse_radius, center + pulse_radius,
            fill='#fca5a5', outline=''  # 浅红色
        )
        
        # 主按钮
        c.create_oval(
            center - radius, center - radius,
            center + radius, center + radius,
            fill=button_color, outline=''
        )
        
        # 简单的波形线条
        wave_color = 'white'
        for i in range(8):
            angle = i * math.pi / 4
            amplitude = 0.3 + 0.2 * math.sin((getattr(self, '_anim_phase', 0) + i) * 0.2)
            inner_r = radius * 0.3
            outer_r = radius * (0.5 + amplitude * 0.3)
            
            start_x = center + int(math.cos(angle) * inner_r)
            start_y = center + int(math.sin(angle) * inner_r)
            end_x = center + int(math.cos(angle) * outer_r)
            end_y = center + int(math.sin(angle) * outer_r)
            
            c.create_line(start_x, start_y, end_x, end_y, 
                         fill=wave_color, width=2)

    def _start_processing_anim(self):
        """开始处理状态动画"""
        logger.info("开始处理状态动画")
        if getattr(self, '_anim_job', None):
            self.window.after_cancel(self._anim_job)
        self._anim_job = None
        self._anim_phase = 0
        self._anim_step()

    def start_processing(self):
        """开始处理状态 - 录音完成后到转录开始之间"""
        logger.info("悬浮窗：开始处理状态")
        self.is_processing = True
        
        if getattr(self, 'icon_canvas', None):
            logger.info("切换到处理状态，启动动画")
            self._start_processing_anim()
        
        # 更新状态标签
        if getattr(self, 'status_label', None):
            self.status_label.configure(text="🔄 正在处理...")

    def stop_processing(self):
        """停止处理状态 - 转录开始时调用"""
        logger.info("悬浮窗：停止处理状态")
        self.is_processing = False
        
        # 停止处理动画
        if getattr(self, '_anim_job', None):
            self.window.after_cancel(self._anim_job)
            self._anim_job = None
        
        # 根据当前状态绘制相应图标
        if getattr(self, 'icon_canvas', None):
            if self.is_recording:
                self._start_recording_anim()
            else:
                self._draw_idle_icon()

    def _start_recording_anim(self):
        """开始录音动画"""
        logger.info("开始录音动画")
        if getattr(self, '_anim_job', None):
            self.window.after_cancel(self._anim_job)
        self._anim_job = None
        self._anim_phase = 0  # 重置动画相位
        self._anim_step()
        
    def _anim_step(self):
        """动画步进 - 支持录音和处理状态"""
        if not getattr(self, 'icon_canvas', None):
            self._anim_job = None
            return
            
        # 更精细的动画相位控制
        self._anim_phase = (self._anim_phase + 1) % 60  # 增加到60帧循环，更平滑
        
        if self.is_recording:
            self._draw_recording_icon()
            # 提高帧率：从100ms改为33ms（约30FPS），更流畅
            self._anim_job = self.window.after(33, self._anim_step)
        elif self.is_processing:
            self._draw_processing_icon()
            # 处理状态动画稍慢一些
            self._anim_job = self.window.after(100, self._anim_step)
        else:
            # 停止动画
            self._draw_idle_icon()
            self._anim_job = None
    
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
            
            # 进入处理状态而不是直接回到静止状态
            self.start_processing()
            
            logger.info("悬浮窗：停止录音")
            
            # 最后调用停止回调，避免回调中的状态更新覆盖我们的UI状态
            self.on_record_stop()
    
    def _toggle_translation(self):
        """切换翻译录音状态"""
        if not self.is_translating:
            # 开始翻译录音
            self.is_translating = True
            if getattr(self, 'translate_button', None):
                self.translate_button.configure(
                    text="⏹️ 停止",
                    bg='#e74c3c'
                )
            if getattr(self, 'status_label', None):
                self.status_label.configure(text="🎤 正在录音 (翻译模式)")
            self.on_translate_start()
            logger.info("悬浮窗：开始翻译录音")
        else:
            # 停止翻译录音
            self.is_translating = False
            if getattr(self, 'translate_button', None):
                self.translate_button.configure(
                    text="🌐 翻译",
                    bg='#e74c3c'
                )
            if getattr(self, 'status_label', None):
                self.status_label.configure(text="🔄 正在翻译...")
            self.on_translate_stop()
            logger.info("悬浮窗：停止翻译录音")
    
    def update_status(self, status_text):
        """更新状态文本"""
        if getattr(self, 'status_label', None):
            self.status_label.configure(text=status_text)

    def set_text(self, text: str):
        """设置显示文本"""
        if getattr(self, 'text_widget', None) is not None:
            self.text_widget.delete('1.0', tk.END)
            if text:
                self.text_widget.insert(tk.END, text)
            # 确保文本输入框获得焦点
            try:
                self.text_widget.focus_set()
            except Exception:
                pass

    def get_text(self) -> str:
        if getattr(self, 'text_widget', None) is not None:
            return self.text_widget.get('1.0', tk.END).rstrip('\n')
        return ""
    
    def reset_state(self):
        """重置状态"""
        self.is_recording = False
        self.is_processing = False
        self.is_translating = False
        
        if getattr(self, 'record_button', None):
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
        
        if getattr(self, 'translate_button', None):
            self.translate_button.configure(
                text="🌐 翻译",
                bg='#e74c3c'
            )
        
        if getattr(self, 'status_label', None):
            self.status_label.configure(text="准备就绪")
            
        # 确保文本框获得焦点
        if hasattr(self, 'text_widget') and self.text_widget:
            self.text_widget.focus_set()
            logger.info("已重新设置焦点到文本框")
    
    def show(self):
        """显示悬浮窗"""
        if self.window:
            self.window.deiconify()
            self.is_visible = True
            self.follow_mouse = False  # 不跟随鼠标移动
            # 确保文本框获得焦点
            if hasattr(self, 'text_widget') and self.text_widget:
                self.text_widget.focus_set()
                logger.info("已设置焦点到文本框")
    
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

    # 添加电平和波形相关方法（简化版本）
    def set_level(self, level: float):
        self._level = level

    def push_wave_samples(self, samples):
        """推入一段实时样本"""
        try:
            if not isinstance(samples, (list, tuple)):
                samples = samples.tolist()
            self._wave_samples.extend(samples)
            if len(self._wave_samples) > self._wave_capacity:
                self._wave_samples = self._wave_samples[-self._wave_capacity:]
        except Exception:
            pass

    def reset_wave(self):
        """清空波形缓存"""
        try:
            self._wave_samples = []
        except Exception:
            pass

    # 简化的内部操作
    def _optimize_text(self):
        """优化文本（占位符）"""
        if getattr(self, 'status_label', None):
            self.status_label.configure(text="✨ 优化功能暂不可用")

    def _write_text(self):
        """写入文本（占位符）"""
        if getattr(self, 'status_label', None):
            self.status_label.configure(text="✍️ 写入功能暂不可用")

    # 简化的计时器相关方法
    def _start_timer(self):
        pass

    def _stop_timer(self):
        pass

    def _tick_timer(self):
        pass