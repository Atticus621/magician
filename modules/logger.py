# -- coding: utf-8 --
"""集中式日志配置 —— 彩色控制台输出。

用法:
    # main.py 启动时调用一次:
    from modules.logger import setup_logging
    setup_logging()

    # 各模块获取 logger:
    import logging
    logger = logging.getLogger(__name__)
    logger.info("message")
"""
import logging
import os

# ANSI 颜色码
COLORS = {
    logging.ERROR:   "\033[91m",  # 红色
    logging.WARNING: "\033[93m",  # 黄色
    logging.INFO:    "\033[0m",   # 白色（默认）
    logging.DEBUG:   "\033[0m",   # 白色（默认）
}
RESET = "\033[0m"


class ColoredFormatter(logging.Formatter):
    """根据日志级别添加 ANSI 颜色的格式化器。"""

    def format(self, record):
        color = COLORS.get(record.levelno, RESET)
        original = super().format(record)
        return f"{color}{original}{RESET}"


def setup_logging(level=logging.INFO):
    """配置根 logger，添加彩色控制台 handler。

    在应用启动时调用一次即可，所有子模块的 logger 会自动继承配置。

    Args:
        level: 最低日志级别，默认 INFO
    """
    os.system("")  # Windows cmd.exe 启用 ANSI 转义处理

    handler = logging.StreamHandler()
    formatter = ColoredFormatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(handler)
