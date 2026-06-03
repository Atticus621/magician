# -- coding: utf-8 --
"""瓶盖检测独立程序 —— 拍照、OCR识别、OK/NG显示。

功能:
  1. 复用 config.json 中的 camera / bottle_cap 配置
  2. 拍照按钮手动采集图像
  3. 曝光时间可调
  4. 检测结果 OK/NG 显示在图像左上角（绿色/红色）
  5. 无分拣功能，纯检测+显示
"""
import sys
import os
import logging
import threading
import tkinter as tk
from tkinter import ttk, filedialog
import cv2
from PIL import Image, ImageTk

# 确保项目根目录在 sys.path 中
_root = os.path.abspath(os.path.dirname(__file__))
if _root not in sys.path:
    sys.path.insert(0, _root)

from modules.config_manager import config
from modules.camera_manager import CameraManager
from modules.cap_detector import process_cap_frame, draw_cap_results

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
logger = logging.getLogger("A")


class CapDetectApp:
    """瓶盖检测应用程序。"""

    def __init__(self):
        self._cam = CameraManager()
        self._root = None
        self._busy = False  # 防止重复点击

        # 从 config.json 读取参数
        cam_cfg = config.camera
        self._device_index = cam_cfg.index if hasattr(cam_cfg, 'index') else 0
        self._exposure_time = cam_cfg.exposure_time if hasattr(cam_cfg, 'exposure_time') else 10000.0

        cap_cfg = config.bottle_cap
        self._cap_config = {
            "diameter_min_mm": cap_cfg.diameter_min_mm if hasattr(cap_cfg, 'diameter_min_mm') else 20,
            "diameter_max_mm": cap_cfg.diameter_max_mm if hasattr(cap_cfg, 'diameter_max_mm') else 40,
            "expiry_date": cap_cfg.expiry_date if hasattr(cap_cfg, 'expiry_date') else "2026/6/6",
            "date_template": cap_cfg.date_template if hasattr(cap_cfg, 'date_template') else "Expiry:*/*/*",
            "pixels_per_mm": 10.0,
        }

    def run(self):
        """显示主窗口（阻塞）。"""
        self._root = tk.Tk()
        self._root.title("瓶盖检测")
        self._root.geometry("1000x700")
        self._root.resizable(True, True)

        # 居中
        self._root.update_idletasks()
        w, h = 1000, 700
        x = (self._root.winfo_screenwidth() - w) // 2
        y = (self._root.winfo_screenheight() - h) // 2
        self._root.geometry(f"{w}x{h}+{x}+{y}")

        self._build_ui()
        self._root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._root.mainloop()

    # ------------------------------------------------------------------
    # UI 构建
    # ------------------------------------------------------------------
    def _build_ui(self):
        root = self._root

        # ── 顶部标题栏 ──
        title_bar = tk.Frame(root, height=45, bg="#2c3e50")
        title_bar.pack(fill=tk.X)
        title_bar.pack_propagate(False)
        tk.Label(title_bar, text="瓶盖检测系统",
                 font=("Microsoft YaHei", 16, "bold"),
                 fg="white", bg="#2c3e50").pack(expand=True)

        # ── 主体区域 ──
        main_frame = tk.Frame(root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=8)
        main_frame.columnconfigure(0, weight=3)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(0, weight=1)

        # ── 左侧：图像显示区 ──
        left_frame = tk.LabelFrame(main_frame, text="  检测画面  ",
                                   font=("Microsoft YaHei", 11, "bold"),
                                   fg="#2c3e50", relief=tk.GROOVE, bd=2)
        left_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        left_frame.rowconfigure(0, weight=1)
        left_frame.columnconfigure(0, weight=1)

        self._canvas = tk.Canvas(left_frame, bg="#1e1e1e", highlightthickness=0)
        self._canvas.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        self._canvas.bind("<Configure>", self._on_canvas_resize)
        self._photo_image = None
        self._cv_image = None

        # ── 右侧：控制面板 ──
        right_frame = tk.LabelFrame(main_frame, text="  控制面板  ",
                                    font=("Microsoft YaHei", 11, "bold"),
                                    fg="#2c3e50", relief=tk.GROOVE, bd=2)
        right_frame.grid(row=0, column=1, sticky="nsew")

        # 状态文本框
        self._text_status = tk.Text(right_frame, font=("Microsoft YaHei", 11),
                                    state=tk.DISABLED, height=5, wrap=tk.WORD,
                                    bg="#f0f0f0", fg="#333333")
        self._text_status.pack(fill=tk.X, padx=10, pady=(12, 8))
        self._set_status("就绪，请点击拍照或加载图片")

        # ── 曝光时间设置 ──
        exposure_frame = tk.LabelFrame(right_frame, text=" 曝光设置 ",
                                       font=("Microsoft YaHei", 9),
                                       fg="#555555", relief=tk.GROOVE, bd=1)
        exposure_frame.pack(padx=10, pady=(0, 8), fill=tk.X)

        exp_input = tk.Frame(exposure_frame)
        exp_input.pack(padx=5, pady=5, fill=tk.X)
        tk.Label(exp_input, text="曝光(μs):",
                 font=("Microsoft YaHei", 9)).pack(side=tk.LEFT)
        self._exposure_var = tk.StringVar(value=str(self._exposure_time))
        tk.Entry(exp_input, textvariable=self._exposure_var,
                 font=("Microsoft YaHei", 9), width=10).pack(side=tk.LEFT, padx=(5, 5))
        tk.Button(exp_input, text="应用", font=("Microsoft YaHei", 9),
                  command=self._apply_exposure).pack(side=tk.LEFT)

        # ── 检测参数 ──
        param_frame = tk.LabelFrame(right_frame, text=" 检测参数 ",
                                    font=("Microsoft YaHei", 9),
                                    fg="#555555", relief=tk.GROOVE, bd=1)
        param_frame.pack(padx=10, pady=(0, 8), fill=tk.X)

        row1 = tk.Frame(param_frame)
        row1.pack(padx=5, pady=3, fill=tk.X)
        tk.Label(row1, text="直径min(mm):", font=("Microsoft YaHei", 9)).pack(side=tk.LEFT)
        self._dmin_var = tk.StringVar(value=str(self._cap_config["diameter_min_mm"]))
        tk.Entry(row1, textvariable=self._dmin_var, font=("Microsoft YaHei", 9),
                 width=6).pack(side=tk.LEFT, padx=(3, 10))
        tk.Label(row1, text="max:", font=("Microsoft YaHei", 9)).pack(side=tk.LEFT)
        self._dmax_var = tk.StringVar(value=str(self._cap_config["diameter_max_mm"]))
        tk.Entry(row1, textvariable=self._dmax_var, font=("Microsoft YaHei", 9),
                 width=6).pack(side=tk.LEFT, padx=(3, 0))

        row2 = tk.Frame(param_frame)
        row2.pack(padx=5, pady=(0, 5), fill=tk.X)
        tk.Label(row2, text="有效期:", font=("Microsoft YaHei", 9)).pack(side=tk.LEFT)
        self._expiry_var = tk.StringVar(value=self._cap_config["expiry_date"])
        tk.Entry(row2, textvariable=self._expiry_var, font=("Microsoft YaHei", 9),
                 width=12).pack(side=tk.LEFT, padx=(3, 0))

        # ── 操作按钮 ──
        btn_frame = tk.Frame(right_frame)
        btn_frame.pack(padx=10, pady=(5, 8), fill=tk.X)

        self._btn_capture = tk.Button(btn_frame, text="拍照检测",
                                      font=("Microsoft YaHei", 12, "bold"),
                                      width=14, height=2,
                                      bg="#2196F3", fg="white",
                                      activebackground="#1976D2",
                                      command=self._on_capture)
        self._btn_capture.pack(pady=(0, 6))

        self._btn_load = tk.Button(btn_frame, text="加载图片",
                                   font=("Microsoft YaHei", 11),
                                   width=14, height=1,
                                   bg="#FF9800", fg="white",
                                   activebackground="#F57C00",
                                   command=self._on_load_image)
        self._btn_load.pack(pady=(0, 6))

        self._btn_open_cam = tk.Button(btn_frame, text="打开相机",
                                       font=("Microsoft YaHei", 11),
                                       width=14, height=1,
                                       bg="#4CAF50", fg="white",
                                       activebackground="#388E3C",
                                       command=self._on_open_camera)
        self._btn_open_cam.pack(pady=(0, 6))

        # ── 日志区 ──
        log_frame = tk.LabelFrame(right_frame, text=" 检测日志 ",
                                  font=("Microsoft YaHei", 9),
                                  fg="#555555", relief=tk.GROOVE, bd=1)
        log_frame.pack(padx=10, pady=(0, 10), fill=tk.BOTH, expand=True)

        self._text_log = tk.Text(log_frame, font=("Consolas", 9),
                                 state=tk.DISABLED, wrap=tk.WORD,
                                 bg="#1e1e1e", fg="#00ff00",
                                 insertbackground="#00ff00", height=8)
        scrollbar = ttk.Scrollbar(log_frame, command=self._text_log.yview)
        self._text_log.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self._text_log.pack(fill=tk.BOTH, expand=True)

    # ------------------------------------------------------------------
    # 文本操作
    # ------------------------------------------------------------------
    def _set_status(self, msg):
        self._text_status.configure(state=tk.NORMAL)
        self._text_status.delete("1.0", tk.END)
        self._text_status.insert(tk.END, msg)
        self._text_status.configure(state=tk.DISABLED)

    def _log(self, msg):
        import time
        ts = time.strftime("%H:%M:%S")
        line = f"[{ts}] {msg}\n"
        self._text_log.configure(state=tk.NORMAL)
        self._text_log.insert(tk.END, line)
        self._text_log.see(tk.END)
        self._text_log.configure(state=tk.DISABLED)

    # ------------------------------------------------------------------
    # 图像显示
    # ------------------------------------------------------------------
    def _show_image(self, cv_img):
        self._cv_image = cv_img
        self._redraw_canvas()

    def _on_canvas_resize(self, event=None):  # noqa: unused-arg
        self._redraw_canvas()

    def _redraw_canvas(self):
        self._canvas.delete("all")
        cw = self._canvas.winfo_width()
        ch = self._canvas.winfo_height()
        if cw < 2 or ch < 2:
            return

        if self._cv_image is None:
            self._canvas.create_text(cw // 2, ch // 2, text="等待拍照...",
                                     fill="#666666", font=("Microsoft YaHei", 14))
            return

        rgb = cv2.cvtColor(self._cv_image, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(rgb)

        iw, ih = pil_img.size
        scale = min(cw / iw, ch / ih)
        new_w, new_h = int(iw * scale), int(ih * scale)
        pil_img = pil_img.resize((new_w, new_h), Image.LANCZOS)

        self._photo_image = ImageTk.PhotoImage(pil_img)
        x = (cw - new_w) // 2
        y = (ch - new_h) // 2
        self._canvas.create_image(x, y, anchor=tk.NW, image=self._photo_image)

    # ------------------------------------------------------------------
    # 绘制 OK/NG 到左上角
    # ------------------------------------------------------------------
    def _draw_status_overlay(self, img, results):
        """在图像左上角绘制总体 OK/NG 结果。

        - 检测到瓶盖且全部OK → 绿色 "OK"
        - 存在NG → 红色 "NG"
        - 未检测到 → 红色 "NG - 未检测到瓶盖"
        """
        overlay = img.copy()

        # 确定总体状态
        if not results:
            status_text = "NG - 未检测到瓶盖"
            color = (0, 0, 255)  # 红色 (BGR)
        else:
            ng_count = sum(1 for r in results if r.get("status") == "NG")
            ok_count = len(results) - ng_count
            if ng_count > 0:
                status_text = f"NG ({ng_count}个不合格)"
                color = (0, 0, 255)  # 红色
            else:
                status_text = f"OK ({ok_count}个合格)"
                color = (0, 255, 0)  # 绿色

        # 左上角背景矩形
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 1.2
        thickness = 2
        (tw, th), _ = cv2.getTextSize(status_text, font, font_scale, thickness)
        pad = 10
        cv2.rectangle(overlay, (0, 0), (tw + pad * 2, th + pad * 2 + 5), (0, 0, 0), -1)
        # 半透明效果
        alpha = 0.6
        cv2.addWeighted(overlay, alpha, img, 1 - alpha, 0, overlay)

        # 绘制文字
        cv2.putText(overlay, status_text, (pad, th + pad),
                    font, font_scale, color, thickness)

        return overlay

    # ------------------------------------------------------------------
    # 读取最新参数
    # ------------------------------------------------------------------
    def _get_cap_config(self):
        """从UI控件读取当前参数。"""
        try:
            dmin = float(self._dmin_var.get())
            dmax = float(self._dmax_var.get())
        except ValueError:
            dmin = self._cap_config["diameter_min_mm"]
            dmax = self._cap_config["diameter_max_mm"]
        return {
            "diameter_min_mm": dmin,
            "diameter_max_mm": dmax,
            "expiry_date": self._expiry_var.get(),
            "date_template": self._cap_config["date_template"],
            "pixels_per_mm": self._cap_config["pixels_per_mm"],
        }

    # ------------------------------------------------------------------
    # 检测处理
    # ------------------------------------------------------------------
    def _process_image(self, img, source=""):
        """对图像执行瓶盖检测并显示结果。"""
        cap_cfg = self._get_cap_config()
        results, _saver = process_cap_frame(img, cap_config=cap_cfg)

        # 绘制检测结果（圆框、标签等）
        annotated = draw_cap_results(img, results)

        # 左上角叠加 OK/NG 总结
        annotated = self._draw_status_overlay(annotated, results)

        # 显示图像
        self._root.after(0, self._show_image, annotated)

        # 输出日志
        if results:
            for i, r in enumerate(results):
                self._root.after(0, self._log, r.get("display", f"瓶盖#{i+1}"))
            ng = sum(1 for r in results if r.get("status") == "NG")
            ok = len(results) - ng
            self._root.after(0, self._set_status,
                             f"{source}检测完成: {len(results)}个瓶盖 (OK:{ok} NG:{ng})")
        else:
            self._root.after(0, self._set_status, f"{source}未检测到瓶盖")
            self._root.after(0, self._log, "未检测到瓶盖")

    # ------------------------------------------------------------------
    # 按钮回调
    # ------------------------------------------------------------------
    def _on_open_camera(self):
        """打开相机按钮。"""
        if self._cam.is_open:
            self._set_status("相机已打开")
            return

        self._btn_open_cam.configure(state=tk.DISABLED)
        self._set_status("正在打开相机...")

        def _run():
            ok = self._cam.open(self._device_index, self._exposure_time)
            msg = "相机打开成功" if ok else "相机打开失败"
            self._root.after(0, self._set_status, msg)
            self._root.after(0, self._log, msg)
            self._root.after(0, lambda: self._btn_open_cam.configure(state=tk.NORMAL))

        threading.Thread(target=_run, daemon=True).start()

    def _apply_exposure(self):
        """应用曝光时间。"""
        try:
            value = float(self._exposure_var.get())
        except ValueError:
            self._set_status("曝光时间格式错误")
            return

        self._exposure_time = value

        if not self._cam.is_open:
            self._set_status(f"相机未打开，曝光时间 {value:.0f}μs 已保存，打开后生效")
            return

        ok = self._cam.set_exposure(value)
        if ok:
            self._set_status(f"曝光时间已设置为 {value:.0f}μs")
            self._log(f"曝光时间: {value:.0f}μs")
        else:
            self._set_status("设置曝光时间失败")

    def _on_capture(self):
        """拍照检测按钮。"""
        if self._busy:
            return

        if not self._cam.is_open:
            self._set_status("请先打开相机")
            return

        self._busy = True
        self._btn_capture.configure(state=tk.DISABLED)
        self._set_status("正在拍照...")

        def _run():
            img = self._cam.grab_frame(timeout_ms=3000)
            if img is None:
                self._root.after(0, self._set_status, "拍照失败，请重试")
                self._root.after(0, self._log, "拍照失败")
                self._root.after(0, lambda: self._btn_capture.configure(state=tk.NORMAL))
                self._busy = False
                return

            self._root.after(0, self._set_status, "正在检测...")
            self._root.after(0, self._log, "拍照成功，开始检测")
            self._process_image(img, "拍照")
            self._busy = False
            self._root.after(0, lambda: self._btn_capture.configure(state=tk.NORMAL))

        threading.Thread(target=_run, daemon=True).start()

    def _on_load_image(self):
        """加载图片检测。"""
        if self._busy:
            return

        file_path = filedialog.askopenfilename(
            title="选择瓶盖图片",
            filetypes=[
                ("图片文件", "*.jpg *.jpeg *.png *.bmp *.tiff"),
                ("所有文件", "*.*"),
            ],
        )
        if not file_path:
            return

        self._busy = True
        self._btn_load.configure(state=tk.DISABLED)
        self._set_status(f"正在加载: {file_path}")

        def _run():
            img = cv2.imread(file_path)
            if img is None:
                self._root.after(0, self._set_status, "图片加载失败")
                self._root.after(0, self._log, f"加载失败: {file_path}")
                self._busy = False
                self._root.after(0, lambda: self._btn_load.configure(state=tk.NORMAL))
                return

            self._root.after(0, self._log, f"加载图片: {os.path.basename(file_path)} ({img.shape[1]}x{img.shape[0]})")
            self._process_image(img, "加载图片")
            self._busy = False
            self._root.after(0, lambda: self._btn_load.configure(state=tk.NORMAL))

        threading.Thread(target=_run, daemon=True).start()

    # ------------------------------------------------------------------
    # 关闭
    # ------------------------------------------------------------------
    def _on_close(self):
        self._cam.close()
        self._root.destroy()


if __name__ == "__main__":
    app = CapDetectApp()
    app.run()
