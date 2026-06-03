# -- coding: utf-8 --
"""人工智能分拣系统 —— 主入口。
模块结构:
  camera/       MVS工业相机SDK封装
  algorithm/    标定转换算法
  robot/        Dobot机械臂控制
  modules/      系统业务模块
    config_manager.py    配置管理（单例）
    camera_manager.py    相机管理
    pcb_detector.py      PCB板检测
    cap_detector.py      瓶盖检测
    sorting_controller.py 分拣控制（相机+视觉+机械臂协调）
    face_module.py       人脸识别（前置摄像头检测）
    login_window.py      登录窗口
    run_window.py        运行窗口
  config.json   场地配置文件（标定参数、坐标、曝光等）
用法:
  conda activate B
  python main.py
"""
import sys
import os
import logging

# 确保项目根目录在 sys.path 中
_root = os.path.abspath(os.path.dirname(__file__))
if _root not in sys.path:
    sys.path.insert(0, _root)

from modules.logger import setup_logging
from modules.config_manager import config
from modules.login_window import LoginWindow
from modules.run_window import RunWindow
from modules.sorting_controller import SortingController
import modules.face_module as face_module

logger = logging.getLogger(__name__)

# ── 全局测试模式 ──
# 开启后：跳过登录验证（无需用户名密码）、人脸识别自动通过、分拣使用模拟数据
TEST_MODE = True


def launch_run_window():
    """登录成功后，打开运行窗口，后台异步初始化相机和机械臂。"""
    logger.info("=" * 50)
    logger.info("人工智能分拣系统启动")
    if TEST_MODE:
        logger.info("【测试模式已开启】")
    logger.info("=" * 50)

    # 创建控制器，不阻塞
    sorter = SortingController()

    # 立即打开运行窗口
    win = RunWindow(sorting_controller=sorter, face_module=face_module,
                    test_mode=TEST_MODE)

    def _on_init_done(camera_ok, robot_ok):
        if not camera_ok:
            logger.warning("相机初始化失败，视觉功能不可用")
        if not robot_ok:
            logger.warning("机械臂连接失败，分拣将使用模拟模式")

    sorter.initialize_async(callback=_on_init_done)

    win.run()

    # 窗口关闭后释放资源
    sorter.shutdown()
    logger.info("系统已退出")


def main():
    """主函数：先显示登录窗口，成功后进入运行窗口。"""
    setup_logging()
    logger.info("标定文件: %s", config.calibration.xml_path)
    login = LoginWindow(on_success=launch_run_window, test_mode=TEST_MODE)
    login.run()


if __name__ == "__main__":
    main()
