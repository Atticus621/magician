# -- coding: utf-8 --
"""登录窗口模块 —— 用户名/密码登录界面。

工艺流程:
  - 输入错误 → 弹出错误提示，点确定关闭
  - 输入 admin / 123456 → 关闭登录窗口，触发 on_success 回调
"""
import tkinter as tk
from tkinter import messagebox


class LoginWindow:
    """登录窗口。"""

    def __init__(self, on_success=None, test_mode=False):
        """
        Args:
            on_success: 登录成功后的回调函数 on_success()
            test_mode: 测试模式，为 True 时跳过登录直接进入
        """
        self._on_success = on_success
        self._root = None
        self._test_mode = test_mode

    def run(self):
        """显示登录窗口（阻塞）。测试模式下跳过登录直接进入。"""
        if self._test_mode:
            if self._on_success:
                self._on_success()
            return

        self._root = tk.Tk()
        self._root.title("系统登录")
        self._root.geometry("400x250")
        self._root.resizable(False, False)

        # 居中显示
        self._root.update_idletasks()
        w, h = 400, 250
        x = (self._root.winfo_screenwidth() - w) // 2
        y = (self._root.winfo_screenheight() - h) // 2
        self._root.geometry(f"{w}x{h}+{x}+{y}")

        # 标题
        title_label = tk.Label(self._root, text="人工智能分拣系统",
                               font=("Microsoft YaHei", 16, "bold"))
        title_label.pack(pady=(20, 15))

        # 用户名行
        frame_user = tk.Frame(self._root)
        frame_user.pack(pady=5)
        lbl_user = tk.Label(frame_user, text="用户名：",
                            font=("Microsoft YaHei", 11), width=8, anchor="e")
        lbl_user.pack(side=tk.LEFT)
        self._entry_user = tk.Entry(frame_user, font=("Microsoft YaHei", 11),
                                    width=20)
        self._entry_user.pack(side=tk.LEFT, padx=(5, 0))

        # 密码行
        frame_pwd = tk.Frame(self._root)
        frame_pwd.pack(pady=5)
        lbl_pwd = tk.Label(frame_pwd, text="密  码：",
                           font=("Microsoft YaHei", 11), width=8, anchor="e")
        lbl_pwd.pack(side=tk.LEFT)
        self._entry_pwd = tk.Entry(frame_pwd, font=("Microsoft YaHei", 11),
                                   width=20, show="*")
        self._entry_pwd.pack(side=tk.LEFT, padx=(5, 0))

        # 登录按钮
        btn_login = tk.Button(self._root, text="登  录",
                              font=("Microsoft YaHei", 12),
                              width=12, command=self._on_login)
        btn_login.pack(pady=(20, 10))

        # 回车绑定
        self._entry_pwd.bind("<Return>", lambda e: self._on_login())
        self._entry_user.focus_set()

        self._root.mainloop()

    def _on_login(self):
        """验证登录凭证。"""
        username = self._entry_user.get().strip()
        password = self._entry_pwd.get().strip()

        if username == "admin" and password == "123456":
            # 登录成功
            self._root.destroy()
            if self._on_success:
                self._on_success()
        else:
            # 登录失败
            messagebox.showerror("登录失败", "用户名或密码错误！")
