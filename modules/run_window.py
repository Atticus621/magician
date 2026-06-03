# -- coding: utf-8 --
"""运行窗口模块 —— 机器人控制平台界面。

布局:
  顶部: 标题 "机器人控制平台"
  左侧: 智能分拣单元（显示物料分拣信息）
  右侧: 控制单元
    - 文本框（状态提示）
    - 测试模式标识（全局开启时显示）
    - 曝光时间输入框
    - 分拣模式下拉菜单
    - 蓝色按钮 "人脸识别"
    - 红色按钮 "物料分拣"（初始灰色不可点击）

状态流转:
  1. 初始 → 文本框"准备就绪，请先进行人脸识别"，分拣按钮红色灰字
  2. 人脸识别成功 → 文本框"识别成功，可以开始分拣"，分拣按钮变绿
  3. 点击物料分拣 → 执行分拣流程，结果显示在左侧

测试模式:
  main.py 中 TEST_MODE 控制登录是否跳过。
  运行窗口中可通过复选框随时开启/关闭，开启后：
  - 人脸识别自动通过
  - 分拣使用模拟数据
  - 曝光时间设置仅显示提示
"""
import os
import tkinter as tk
from tkinter import ttk, filedialog
import threading
import time
import cv2
from PIL import Image, ImageTk
from modules.config_manager import config as app_config


class RunWindow:
    """运行窗口。"""

    def __init__(self, sorting_controller=None, face_module=None, test_mode=False):
        """
        Args:
            sorting_controller: SortingController 实例
            face_module: face_module 模块引用
            test_mode: 全局测试模式标志
        """
        self._sorter = sorting_controller
        self._face = face_module
        self._root = None
        self._face_verified = False
        self._sorting = False
        self._pending_results = None  # 拍照识别后暂存的分拣结果
        self._test_mode_init = test_mode  # 初始值，run() 中创建 BooleanVar

        # 人脸识别配置
        face_cfg = app_config.face if hasattr(app_config, 'face') else None
        self._face_threshold = face_cfg.match_threshold if face_cfg and hasattr(face_cfg, 'match_threshold') else 60
        self._session_number = face_cfg.session_number if face_cfg and hasattr(face_cfg, 'session_number') else 0
        self._team_number = face_cfg.team_number if face_cfg and hasattr(face_cfg, 'team_number') else 0

    def run(self):
        """显示运行窗口（阻塞）。"""
        self._root = tk.Tk()
        self._test_mode = tk.BooleanVar(value=self._test_mode_init)
        self._root.title("机器人控制平台")
        self._root.geometry("1050x650")
        self._root.resizable(True, True)

        # 居中
        self._root.update_idletasks()
        w, h = 1050, 650
        x = (self._root.winfo_screenwidth() - w) // 2
        y = (self._root.winfo_screenheight() - h) // 2
        self._root.geometry(f"{w}x{h}+{x}+{y}")

        self._build_ui()

        # 初始化人脸训练数据
        if self._face is not None:
            face_data_dir = os.path.join(
                os.path.abspath(os.path.join(os.path.dirname(__file__), "..")),
                "face_data")
            try:
                ok = self._face.init_face_recognition(face_data_dir)
                if ok:
                    self._set_info("人脸数据已加载，请进行人脸识别")
                else:
                    self._set_info("未找到人脸训练数据，将仅做检测")
            except Exception as e:
                self._set_info(f"人脸数据加载失败: {e}")

        self._root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._root.mainloop()

    # ------------------------------------------------------------------
    # UI构建
    # ------------------------------------------------------------------
    def _build_ui(self):
        root = self._root

        # ── 顶部标题 ──
        title_bar = tk.Frame(root, height=50, bg="#2c3e50")
        title_bar.pack(fill=tk.X)
        title_bar.pack_propagate(False)
        tk.Label(title_bar, text="机器人控制平台",
                 font=("Microsoft YaHei", 18, "bold"),
                 fg="white", bg="#2c3e50").pack(expand=True)

        # ── 主体区域：左右两栏 ──
        main_frame = tk.Frame(root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=10)
        main_frame.columnconfigure(0, weight=3)
        main_frame.columnconfigure(1, weight=2)
        main_frame.rowconfigure(0, weight=1)

        # ── 左侧：智能分拣单元 ──
        left_frame = tk.LabelFrame(main_frame, text="  智能分拣单元  ",
                                   font=("Microsoft YaHei", 12, "bold"),
                                   fg="#2c3e50", relief=tk.GROOVE, bd=2)
        left_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        left_frame.rowconfigure(0, weight=5)
        left_frame.rowconfigure(1, weight=1)
        left_frame.columnconfigure(0, weight=1)

        # 图像显示区
        self._canvas = tk.Canvas(left_frame, bg="#1e1e1e", highlightthickness=0)
        self._canvas.grid(row=0, column=0, sticky="nsew", padx=5, pady=(5, 2))
        self._canvas.bind("<Configure>", self._on_canvas_resize)
        self._photo_image = None  # 保持引用防止GC
        self._cv_image = None     # 暂存当前标注图（用于缩放重绘）

        # 文本日志区
        text_frame = tk.Frame(left_frame)
        text_frame.grid(row=1, column=0, sticky="nsew", padx=5, pady=(2, 5))
        self._text_data = tk.Text(text_frame, font=("Consolas", 10),
                                  state=tk.DISABLED, wrap=tk.WORD, bg="#1e1e1e",
                                  fg="#00ff00", insertbackground="#00ff00",
                                  height=5)
        scrollbar = ttk.Scrollbar(text_frame, command=self._text_data.yview)
        self._text_data.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self._text_data.pack(fill=tk.BOTH, expand=True)

        # ── 右侧：控制单元 ──
        right_frame = tk.LabelFrame(main_frame, text="  控制单元  ",
                                    font=("Microsoft YaHei", 12, "bold"),
                                    fg="#2c3e50", relief=tk.GROOVE, bd=2)
        right_frame.grid(row=0, column=1, sticky="nsew")

        # 状态文本框
        self._text_status = tk.Text(right_frame, font=("Microsoft YaHei", 12),
                                    state=tk.DISABLED, height=6, wrap=tk.WORD,
                                    bg="#f0f0f0", fg="#333333")
        self._text_status.pack(fill=tk.X, padx=10, pady=(15, 10))
        self._set_status("准备就绪，请先进行人脸识别")

        # 测试模式开关（可随时切换）
        chk_test = tk.Checkbutton(right_frame, text="测试模式",
                                  font=("Microsoft YaHei", 10),
                                  variable=self._test_mode,
                                  onvalue=True, offvalue=False)
        chk_test.pack(padx=10, pady=(0, 5), anchor="e")

        # 曝光时间设置
        exposure_frame = tk.Frame(right_frame)
        exposure_frame.pack(padx=10, pady=(0, 5), fill=tk.X)
        tk.Label(exposure_frame, text="曝光时间(μs):",
                 font=("Microsoft YaHei", 10)).pack(side=tk.LEFT)
        self._exposure_var = tk.StringVar(
            value=str(self._sorter._exposure_time) if self._sorter else "20000")
        exposure_entry = tk.Entry(exposure_frame, textvariable=self._exposure_var,
                                  font=("Microsoft YaHei", 10), width=10)
        exposure_entry.pack(side=tk.LEFT, padx=(5, 5))
        tk.Button(exposure_frame, text="应用", font=("Microsoft YaHei", 9),
                  command=self._apply_exposure).pack(side=tk.LEFT)

        # 分拣模式下拉菜单
        mode_frame = tk.Frame(right_frame)
        mode_frame.pack(padx=10, pady=(0, 5), anchor="w")
        tk.Label(mode_frame, text="分拣模式:",
                 font=("Microsoft YaHei", 10)).pack(side=tk.LEFT)
        self._sort_mode_var = tk.StringVar(value="PCB分拣")
        mode_menu = ttk.Combobox(mode_frame, textvariable=self._sort_mode_var,
                                 values=["PCB分拣", "瓶盖分拣", "水果分拣"],
                                 state="readonly", width=10,
                                 font=("Microsoft YaHei", 10))
        mode_menu.pack(side=tk.LEFT, padx=(5, 0))
        mode_menu.bind("<<ComboboxSelected>>", self._on_mode_change)

        # 回零参数
        home_frame = tk.LabelFrame(right_frame, text="回零参数",
                                   font=("Microsoft YaHei", 9),
                                   fg="#555555", relief=tk.GROOVE, bd=1)
        home_frame.pack(padx=10, pady=(0, 5), fill=tk.X)

        home_input = tk.Frame(home_frame)
        home_input.pack(padx=5, pady=3, fill=tk.X)

        self._home_vars = {}
        _home_defaults = {}
        if self._sorter:
            _home_defaults = {
                "X": self._sorter._home_x,
                "Y": self._sorter._home_y,
                "Z": self._sorter._home_z,
                "R": self._sorter._home_r,
            }
        for i, (label, default) in enumerate(_home_defaults.items()):
            tk.Label(home_input, text=f"{label}:",
                     font=("Microsoft YaHei", 9)).grid(row=0, column=i*2, padx=(5, 1))
            var = tk.StringVar(value=str(default))
            self._home_vars[label] = var
            tk.Entry(home_input, textvariable=var,
                     font=("Microsoft YaHei", 9), width=5).grid(row=0, column=i*2+1, padx=(0, 3))

        btn_row = tk.Frame(home_frame)
        btn_row.pack(padx=5, pady=(0, 3), fill=tk.X)
        tk.Button(btn_row, text="应用参数", font=("Microsoft YaHei", 9),
                  command=self._apply_home_params).pack(side=tk.LEFT, padx=(0, 5))
        tk.Button(btn_row, text="回零", font=("Microsoft YaHei", 9, "bold"),
                  bg="#9C27B0", fg="white", activebackground="#7B1FA2",
                  command=self._on_go_home).pack(side=tk.LEFT)

        # 机械臂控制按钮（清除警报 + 急停）
        robot_btn_frame = tk.Frame(right_frame)
        robot_btn_frame.pack(padx=10, pady=(0, 5), fill=tk.X)
        tk.Button(robot_btn_frame, text="清除警报",
                  font=("Microsoft YaHei", 10, "bold"),
                  bg="#FF9800", fg="white", activebackground="#F57C00",
                  width=9, command=self._on_clear_alarm).pack(side=tk.LEFT, padx=(0, 5))
        tk.Button(robot_btn_frame, text="急停",
                  font=("Microsoft YaHei", 10, "bold"),
                  bg="#D32F2F", fg="white", activebackground="#B71C1C",
                  width=9, command=self._on_emergency_stop).pack(side=tk.LEFT)

        # 队伍信息显示区（人脸识别按钮上方）
        self._info_frame = tk.Frame(right_frame, bg="#e8e8e8", relief=tk.GROOVE, bd=1)
        self._info_frame.pack(padx=10, pady=(5, 8), fill=tk.X)
        self._label_info = tk.Label(self._info_frame,
                                    text="等待人脸识别...",
                                    font=("Microsoft YaHei", 13, "bold"),
                                    bg="#e8e8e8", fg="#333333",
                                    anchor="center", height=2)
        self._label_info.pack(fill=tk.X, padx=5, pady=5)

        # 人脸识别按钮（蓝色）
        self._btn_face = tk.Button(right_frame, text="人脸识别",
                                   font=("Microsoft YaHei", 13, "bold"),
                                   width=18, height=2,
                                   bg="#2196F3", fg="white",
                                   activebackground="#1976D2",
                                   relief=tk.RAISED, bd=2,
                                   command=self._on_face_detect)
        self._btn_face.pack(padx=10, pady=(20, 10))

        # 物料分拣按钮（红色，初始文字灰色表示不可用）
        self._btn_sort = tk.Button(right_frame, text="物料分拣",
                                   font=("Microsoft YaHei", 13, "bold"),
                                   width=18, height=2,
                                   bg="#f44336", fg="#999999",
                                   relief=tk.RAISED, bd=2,
                                   command=self._on_sorting)
        self._btn_sort.pack(padx=10, pady=(0, 5))

        # 确认分拣按钮（橙色，初始隐藏）
        self._btn_confirm = tk.Button(right_frame, text="确认分拣",
                                      font=("Microsoft YaHei", 13, "bold"),
                                      width=18, height=2,
                                      bg="#FF9800", fg="white",
                                      activebackground="#F57C00",
                                      relief=tk.RAISED, bd=2,
                                      command=self._on_confirm_sort)
        # 初始不显示，拍照识别成功后才出现

    # ------------------------------------------------------------------
    # 图像显示
    # ------------------------------------------------------------------
    def _show_image(self, cv_img):
        """在Canvas上显示OpenCV BGR图像，自适应缩放居中。"""
        self._cv_image = cv_img
        self._redraw_canvas()

    def _on_canvas_resize(self, event=None):
        """Canvas大小变化时重绘图像。"""
        self._redraw_canvas()

    def _redraw_canvas(self):
        """将 _cv_image 按Canvas尺寸等比缩放居中绘制。"""
        self._canvas.delete("all")
        cw = self._canvas.winfo_width()
        ch = self._canvas.winfo_height()
        if cw < 2 or ch < 2:
            return

        if self._cv_image is None:
            # 无图像时显示提示
            self._canvas.create_text(cw // 2, ch // 2, text="等待拍照...",
                                     fill="#666666", font=("Microsoft YaHei", 14))
            return

        # BGR → RGB → PIL
        rgb = cv2.cvtColor(self._cv_image, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(rgb)

        # 等比缩放
        iw, ih = pil_img.size
        scale = min(cw / iw, ch / ih)
        new_w, new_h = int(iw * scale), int(ih * scale)
        pil_img = pil_img.resize((new_w, new_h), Image.LANCZOS)

        self._photo_image = ImageTk.PhotoImage(pil_img)
        x = (cw - new_w) // 2
        y = (ch - new_h) // 2
        self._canvas.create_image(x, y, anchor=tk.NW, image=self._photo_image)

    # ------------------------------------------------------------------
    # 状态文本框操作
    # ------------------------------------------------------------------
    def _set_status(self, msg):
        """设置状态文本框内容。"""
        self._text_status.configure(state=tk.NORMAL)
        self._text_status.delete("1.0", tk.END)
        self._text_status.insert(tk.END, msg)
        self._text_status.configure(state=tk.DISABLED)

    def _set_info(self, text, fg="#333333", bg="#e8e8e8"):
        """设置队伍信息显示标签。"""
        self._label_info.configure(text=text, fg=fg, bg=bg)
        self._info_frame.configure(bg=bg)

    def _log_data(self, msg):
        """向左侧分拣显示区追加一行。"""
        timestamp = time.strftime("%H:%M:%S")
        line = f"[{timestamp}] {msg}\n"
        self._text_data.configure(state=tk.NORMAL)
        self._text_data.insert(tk.END, line)
        self._text_data.see(tk.END)
        self._text_data.configure(state=tk.DISABLED)

    # ------------------------------------------------------------------
    # 人脸识别（前置摄像头，只需检测到人脸）
    # ------------------------------------------------------------------
    def _on_face_detect(self):
        """人脸识别按钮回调。"""
        # 测试模式：跳过摄像头，直接模拟通过
        if self._test_mode.get():
            self._set_status("[测试模式] 模拟人脸识别通过")
            self._on_face_result({
                "detected": True, "matched": True,
                "name": "测试用户", "confidence": 95.0,
            })
            return

        if self._face is None:
            self._set_status("人脸识别模块未加载")
            return

        self._btn_face.configure(state=tk.DISABLED)
        self._set_info("正在识别，请正对摄像头...", fg="#1976D2")
        self._set_status("正在打开摄像头，请正对屏幕...")

        def _run():
            result = self._face.detect_face(
                callback=lambda msg: self._root.after(0, self._set_status, msg),
                recognizer_enabled=True,
                match_threshold=self._face_threshold,
            )
            self._root.after(0, self._on_face_result, result)

        threading.Thread(target=_run, daemon=True).start()

    def _on_face_result(self, result):
        """人脸识别结果处理。

        Args:
            result: dict {detected, matched, name, confidence} 或 bool（兼容旧模式）
        """
        # 兼容旧的 bool 返回值
        if isinstance(result, bool):
            result = {
                "detected": result, "matched": result,
                "name": "未知", "confidence": 100.0 if result else 0.0,
            }

        detected = result.get("detected", False)
        confidence = result.get("confidence", 0.0)
        name = result.get("name", "")

        if detected and confidence >= self._face_threshold:
            self._face_verified = True
            self._set_status("识别成功，可以开始分拣")
            self._btn_sort.configure(bg="#4CAF50", fg="white",
                                     activebackground="#388E3C")
            self._btn_face.configure(state=tk.NORMAL)
            self._log_data(f"人脸识别通过: {name}, 匹配度: {confidence:.1f}%")

            # 短暂显示 "人脸识别通过，匹配度：XX%"
            pass_text = f"人脸识别通过\n匹配度：{confidence:.1f}%"
            self._set_info(pass_text, fg="#FFFFFF", bg="#4CAF50")

            # 2秒后显示队伍信息
            def _show_team():
                team_text = f"场次号：{self._session_number}\n队伍号：{self._team_number}"
                self._set_info(team_text, fg="#1B5E20", bg="#C8E6C9")

            self._root.after(2000, _show_team)

        elif detected:
            # 检测到人脸但匹配度不足
            self._set_status(f"匹配度不足 ({confidence:.1f}%)，请重试")
            self._set_info(f"匹配度不足\n{confidence:.1f}% < {self._face_threshold}%",
                           fg="#FFFFFF", bg="#FF9800")
            self._btn_face.configure(state=tk.NORMAL)
            self._log_data(f"匹配度不足: {name}, {confidence:.1f}%")
        else:
            self._set_status("未检测到人脸，请重试")
            self._set_info("未检测到人脸", fg="#FFFFFF", bg="#f44336")
            self._btn_face.configure(state=tk.NORMAL)
            self._log_data("人脸识别失败：未检测到人脸")

    # ------------------------------------------------------------------
    # 分拣模式切换
    # ------------------------------------------------------------------
    def _on_mode_change(self, event=None):
        """下拉菜单切换分拣模式。"""
        mode_text = self._sort_mode_var.get()
        if mode_text == "瓶盖分拣":
            mode = "cap"
        elif mode_text == "水果分拣":
            mode = "fruit"
        else:
            mode = "pcb"

        if self._sorter:
            self._sorter.set_mode(mode)

        self._log_data(f"切换分拣模式: {mode_text}")

    # ------------------------------------------------------------------
    # 曝光时间设置
    # ------------------------------------------------------------------
    def _apply_exposure(self):
        """应用曝光时间设置。"""
        try:
            value = float(self._exposure_var.get())
        except ValueError:
            self._set_status("曝光时间格式错误，请输入数字")
            return

        if self._sorter is None:
            self._set_status("分拣控制器未加载")
            return

        if self._test_mode.get():
            self._set_status(f"[测试模式] 曝光时间已设置为 {value:.0f} μs")
            self._log_data(f"曝光时间设置为 {value:.0f} μs")
            return

        if not self._sorter.camera_ready:
            # 相机未就绪，先保存值，连接后自动生效
            self._sorter._exposure_time = value
            self._set_status(f"相机正在连接中，曝光时间 {value:.0f} μs 将在连接后生效")
            return

        ok = self._sorter.set_exposure(value)
        if ok:
            self._set_status(f"曝光时间已设置为 {value:.0f} μs")
            self._log_data(f"曝光时间设置为 {value:.0f} μs")
        else:
            self._set_status("设置曝光时间失败")

    # ------------------------------------------------------------------
    # 回零
    # ------------------------------------------------------------------
    def _apply_home_params(self):
        """应用回零参数。"""
        if self._sorter is None:
            self._set_status("分拣控制器未加载")
            return
        try:
            x = int(self._home_vars["X"].get())
            y = int(self._home_vars["Y"].get())
            z = int(self._home_vars["Z"].get())
            r = int(self._home_vars["R"].get())
        except ValueError:
            self._set_status("回零参数格式错误，请输入整数")
            return
        self._sorter.set_home_params(x, y, z, r)
        self._set_status(f"回零参数已更新: ({x}, {y}, {z}, {r})")

    def _on_go_home(self):
        """回零按钮回调。"""
        if self._sorting:
            return

        if self._test_mode.get():
            self._set_status("[测试模式] 模拟回零完成")
            self._log_data("回零完成")
            return

        if self._sorter is None:
            self._set_status("分拣控制器未加载")
            return

        self._sorting = True
        self._set_status("正在回零...")

        def _callback(msg):
            self._root.after(0, self._set_status, msg)
            self._root.after(0, self._log_data, msg)

        def _run():
            self._sorter.go_home(callback=_callback)
            self._root.after(0, self._on_go_home_done)

        threading.Thread(target=_run, daemon=True).start()

    def _on_go_home_done(self):
        """回零完成。"""
        self._sorting = False

    # ------------------------------------------------------------------
    # 机械臂控制（清除警报 + 急停）
    # ------------------------------------------------------------------
    def _on_clear_alarm(self):
        """清除警报按钮回调。"""
        if self._sorter is None:
            self._set_status("分拣控制器未加载")
            return

        self._set_status("正在清除警报...")
        self._log_data("正在清除警报...")

        def _callback(msg):
            self._root.after(0, self._set_status, msg)
            self._root.after(0, self._log_data, msg)

        def _run():
            self._sorter.clear_alarm(callback=_callback)

        threading.Thread(target=_run, daemon=True).start()

    def _on_emergency_stop(self):
        """急停按钮回调。"""
        if self._sorter is None:
            self._set_status("分拣控制器未加载")
            return

        self._sorting = False
        self._pending_results = None
        self._set_status("急停触发！")
        self._log_data("=== 急停触发 ===")

        def _callback(msg):
            self._root.after(0, self._set_status, msg)
            self._root.after(0, self._log_data, msg)

        def _run():
            self._sorter.emergency_stop(callback=_callback)
            self._root.after(0, self._on_emergency_done)

        threading.Thread(target=_run, daemon=True).start()

    def _on_emergency_done(self):
        """急停完成后恢复按钮状态。"""
        self._btn_sort.configure(bg="#4CAF50", fg="white")
        self._btn_confirm.pack_forget()

    # ------------------------------------------------------------------
    # 物料分拣（两步：先拍照识别，再确认分拣）
    # ------------------------------------------------------------------
    def _on_sorting(self):
        """物料分拣按钮回调 —— 第一步：拍照识别。"""
        if not self._face_verified:
            self._set_status("请先进行人脸识别")
            return

        if self._sorting:
            return

        self._sorting = True
        self._pending_results = None
        self._btn_sort.configure(bg="#999999", fg="#cccccc")
        self._btn_confirm.pack_forget()  # 隐藏确认按钮
        self._set_status("正在拍照识别...")

        # 测试模式：加载本地图片进行检测
        if self._test_mode.get():
            if self._sorter is None:
                self._sorting = False
                self._btn_sort.configure(bg="#4CAF50", fg="white")
                self._set_status("分拣控制器未加载")
                return

            # 弹出文件选择对话框
            file_path = filedialog.askopenfilename(
                title="选择测试图片",
                filetypes=[
                    ("图片文件", "*.jpg *.jpeg *.png *.bmp *.tiff"),
                    ("所有文件", "*.*"),
                ],
            )
            if not file_path:
                self._sorting = False
                self._btn_sort.configure(bg="#4CAF50", fg="white")
                self._set_status("已取消")
                return

            self._set_status(f"[测试模式] 正在加载: {file_path}")

            def _run():
                img = cv2.imread(file_path)
                if img is None:
                    self._root.after(0, self._on_sort_message,
                                     f"[测试模式] 图片加载失败: {file_path}")
                    self._root.after(0, self._on_capture_complete, [], None)
                    return

                self._root.after(0, self._on_sort_message,
                                 f"[测试模式] 图片加载成功: {img.shape[1]}x{img.shape[0]}")

                # 根据当前模式调用对应检测函数
                mode = self._sorter.sort_mode_name
                detect_config = self._sorter._detect_config.copy()
                detect_config["pixels_per_mm"] = self._sorter.calibrator.pixels_per_mm

                self._root.after(0, self._on_sort_message,
                                 f"[测试模式] 正在识别...")

                results, saver = self._sorter._detect_func(
                    img, self._sorter.calibrator, detect_config)
                annotated = self._sorter._draw_func(img, results)

                for item in results:
                    self._root.after(0, self._on_sort_message, item["display"])

                self._root.after(0, self._on_capture_complete, results, annotated)

            threading.Thread(target=_run, daemon=True).start()
            return

        # 正常模式：调用拍照识别
        if self._sorter is None:
            self._sorting = False
            self._btn_sort.configure(bg="#4CAF50", fg="white")
            self._set_status("分拣控制器未加载")
            return

        def _callback(msg):
            self._root.after(0, self._on_sort_message, msg)

        def _run():
            results, annotated_img = self._sorter.capture_and_identify(callback=_callback)
            self._root.after(0, self._on_capture_complete, results, annotated_img)

        threading.Thread(target=_run, daemon=True).start()

    def _on_capture_complete(self, results, annotated_img=None):
        """拍照识别完成，显示标注图像和确认分拣按钮。"""
        self._pending_results = results
        self._sorting = False

        # 显示标注后的图像
        if annotated_img is not None:
            self._show_image(annotated_img)

        mode = self._sorter.sort_mode_name if self._sorter else "pcb"
        item_name = {"cap": "瓶盖", "fruit": "水果"}.get(mode, "PCB板")

        if results:
            self._set_status(f"识别到 {len(results)} 个{item_name}，请点击【确认分拣】执行")
            self._btn_confirm.pack(padx=10, pady=(0, 20))
        else:
            self._set_status(f"未检测到{item_name}，请重新拍照")
            self._btn_sort.configure(bg="#4CAF50", fg="white")

    def _on_confirm_sort(self):
        """确认分拣按钮回调 —— 第二步：控制机械臂分拣。"""
        if self._pending_results is None:
            self._set_status("请先拍照识别")
            return

        if self._sorting:
            return

        self._sorting = True
        self._btn_confirm.pack_forget()
        self._btn_sort.configure(bg="#999999", fg="#cccccc")
        self._set_status("正在执行分拣...")

        # 测试模式：模拟分拣执行
        if self._test_mode.get():
            def _run():
                self._root.after(0, self._on_sort_message,
                                 "[测试模式] 分拣完成 → 目标位置(200,110,20)")
                self._root.after(0, self._on_sort_complete)
            threading.Thread(target=_run, daemon=True).start()
            return

        # 正常模式：执行机械臂分拣
        def _callback(msg):
            self._root.after(0, self._on_sort_message, msg)

        def _run():
            self._sorter.execute_sort(self._pending_results, callback=_callback)
            self._root.after(0, self._on_sort_complete)

        threading.Thread(target=_run, daemon=True).start()

    def _on_sort_message(self, msg):
        """分拣过程中的状态消息。"""
        self._set_status(msg)
        # 物料信息也显示在左侧分拣区
        if "(接收)" in msg or "(瓶盖)" in msg or "(水果)" in msg or "Expiry" in msg or "分拣" in msg:
            self._log_data(msg)

    def _on_sort_complete(self):
        """分拣完成。"""
        self._sorting = False
        self._pending_results = None
        self._set_status("分拣完成，可以继续分拣")
        self._btn_sort.configure(bg="#4CAF50", fg="white")
        self._btn_confirm.pack_forget()
        self._log_data("分拣流程完成")

    # ------------------------------------------------------------------
    # 关闭
    # ------------------------------------------------------------------
    def _on_close(self):
        if self._sorting:
            self._sorting = False
        if self._sorter:
            self._sorter.shutdown()
        self._root.destroy()

    # ------------------------------------------------------------------
    # 关闭
    # ------------------------------------------------------------------
    def _on_close(self):
        if self._sorting:
            self._sorting = False
        if self._sorter:
            self._sorter.shutdown()
        self._root.destroy()
