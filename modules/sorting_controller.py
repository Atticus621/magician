# -- coding: utf-8 --
"""分拣控制模块 —— 协调相机拍摄、视觉识别、机械臂分拣。

工作流程:
  1. 相机拍摄一帧
  2. 调用对应检测器（PCB/瓶盖）识别物料
  3. 调用分拣模式获取目标位置
  4. 控制机械臂分拣到目标位置

配置: 所有参数从 config.json 读取，换场地只需修改配置文件。
"""
import sys
import os
import time
import threading
import logging

_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _root not in sys.path:
    sys.path.insert(0, _root)

import robot.DobotDllType as dType
from modules.camera_manager import CameraManager
from modules.pcb_detector import process_frame as pcb_process, draw_results as pcb_draw
from modules.cap_detector import process_cap_frame as cap_process, draw_cap_results as cap_draw
from modules.fruit_detector import process_fruit_frame as fruit_process, draw_fruit_results as fruit_draw, preload_yolo_model
from modules.sort_modes import create_sort_mode
from modules.image_saver import ImageSaver
from modules.config_manager import config as app_config
from algorithm.calibration import Calibrator

logger = logging.getLogger(__name__)


class SortingController:
    """分拣控制器，协调相机、视觉、机械臂。"""

    def __init__(self):
        self.camera = CameraManager()
        self.calibrator = Calibrator()
        self._api = None
        self._robot_connected = False
        self._running = False
        self._thread = None
        self._sort_mode = None
        self._detect_func = None
        self._draw_func = None
        self._detect_config = None
        self._mode_name = "pcb"
        self._loop = False
        self._camera_ready = False
        self._robot_ready = False
        self._init_lock = threading.Lock()

        # 从配置读取参数
        self._init_from_config()

    def _init_from_config(self):
        """从配置文件初始化参数。"""
        # 机械臂连接参数
        self._com_port = app_config.robot.com_port
        self._baudrate = app_config.robot.baudrate
        self._home_x = app_config.robot.get("home_x", 200)
        self._home_y = app_config.robot.get("home_y", 0)
        self._home_z = app_config.robot.get("home_z", 40)
        self._home_r = app_config.robot.get("home_r", 0)

        # 相机参数
        self._camera_index = app_config.camera.index
        self._exposure_time = app_config.camera.exposure_time

        # 标定参数
        self._cal_xml_path = app_config.calibration.xml_path

    # ------------------------------------------------------------------
    # 分拣模式
    # ------------------------------------------------------------------
    @property
    def sort_mode_name(self):
        """当前分拣模式名称: 'pcb' 或 'cap'"""
        return self._mode_name

    @property
    def loop_enabled(self):
        """当前模式是否启用循环分拣。"""
        return self._loop

    @property
    def camera_ready(self):
        """相机是否已就绪。"""
        return self._camera_ready

    @property
    def robot_ready(self):
        """机械臂是否已就绪。"""
        return self._robot_ready

    def set_mode(self, mode_name):
        """设置分拣模式。

        Args:
            mode_name: "pcb"、"cap" 或 "fruit"
        """
        if mode_name == "cap":
            cap_cfg = app_config.bottle_cap.to_dict()
            self._sort_mode = create_sort_mode("dual_area", cap_cfg)
            self._detect_func = cap_process
            self._draw_func = cap_draw
            self._detect_config = cap_cfg
            self._mode_name = "cap"
            self._loop = app_config.bottle_cap.get("loop", False)
            logger.info("分拣模式切换为: 瓶盖（双区域）, 循环=%s", self._loop)
        elif mode_name == "fruit":
            fruit_cfg = app_config.fruit.to_dict()
            self._sort_mode = create_sort_mode("dual_area", fruit_cfg)
            self._detect_func = fruit_process
            self._draw_func = fruit_draw
            self._detect_config = fruit_cfg
            self._mode_name = "fruit"
            self._loop = app_config.fruit.get("loop", False)
            logger.info("分拣模式切换为: 水果（YOLO分类）, 循环=%s", self._loop)
        else:
            pcb_cfg = app_config.pcb.to_dict()
            self._sort_mode = create_sort_mode("simple", pcb_cfg)
            self._detect_func = pcb_process
            self._draw_func = pcb_draw
            self._detect_config = pcb_cfg
            self._mode_name = "pcb"
            self._loop = app_config.pcb.get("loop", False)
            logger.info("分拣模式切换为: PCB板（单目标）, 循环=%s", self._loop)

    # ------------------------------------------------------------------
    # 曝光时间
    # ------------------------------------------------------------------
    def set_exposure(self, exposure_time: float) -> bool:
        """动态设置相机曝光时间。成功返回 True。"""
        self._exposure_time = exposure_time
        if not self._camera_ready:
            logger.warning("相机未就绪，曝光时间将在连接后生效")
            return False
        return self.camera.set_exposure(exposure_time)

    # ------------------------------------------------------------------
    # 初始化（后台线程）
    # ------------------------------------------------------------------
    def initialize_async(self, callback=None):
        """后台线程初始化相机和机械臂。

        Args:
            callback: callback(camera_ok, robot_ok) 初始化完成后回调
        """
        def _run():
            camera_ok, robot_ok = self._do_initialize()
            if callback:
                callback(camera_ok, robot_ok)
        threading.Thread(target=_run, daemon=True).start()

    def _do_initialize(self):
        """实际初始化逻辑（在后台线程中执行）。"""
        with self._init_lock:
            # 加载标定（快速，不阻塞）
            try:
                if self._cal_xml_path:
                    self.calibrator.load_from_xml(self._cal_xml_path)
                    logger.info("标定矩阵加载成功")
                else:
                    logger.warning("未配置标定XML路径")
            except Exception as e:
                logger.error("标定失败: %s", e)

            # 默认使用PCB模式
            if self._sort_mode is None:
                self.set_mode("pcb")

            # 预加载 YOLO 模型
            try:
                model = preload_yolo_model()
                if model:
                    logger.info("YOLO模型预加载成功")
                else:
                    logger.warning("YOLO模型预加载失败，水果分类将不可用")
            except Exception as e:
                logger.warning("YOLO模型预加载异常: %s", e)

            # 初始化相机
            camera_ok = self.camera.open(self._camera_index, self._exposure_time)
            self._camera_ready = camera_ok

            # 连接机械臂
            robot_ok = self._connect_robot(self._com_port, self._baudrate)
            self._robot_ready = robot_ok

            return camera_ok, robot_ok

    def ensure_camera(self):
        """确保相机已就绪。未就绪则尝试初始化，返回是否可用。"""
        if self._camera_ready:
            return True
        with self._init_lock:
            if self._camera_ready:
                return True
            ok = self.camera.open(self._camera_index, self._exposure_time)
            self._camera_ready = ok
            return ok

    def ensure_robot(self):
        """确保机械臂已就绪。未就绪则尝试初始化，返回是否可用。"""
        if self._robot_ready:
            return True
        logger.info("[机械臂] 尝试重新连接...")
        with self._init_lock:
            if self._robot_ready:
                return True
            ok = self._connect_robot(self._com_port, self._baudrate)
            self._robot_ready = ok
            if ok:
                logger.info("[机械臂] 重连成功")
            else:
                logger.error("[机械臂] 重连失败")
            return ok

    def _connect_robot(self, com_port, baudrate):
        """连接Dobot机械臂。"""
        logger.info("[机械臂] 正在连接 %s (波特率 %d)...", com_port, baudrate)
        try:
            self._api = dType.load()
            logger.debug("[机械臂] DLL加载完成")
            state = dType.ConnectDobot(self._api, com_port, baudrate)[0]
            if state == dType.DobotConnect.DobotConnect_NoError:
                self._robot_connected = True
                logger.info("[机械臂] 连接成功，正在初始化参数...")
                dType.SetHOMEParams(self._api,
                    self._home_x, self._home_y, self._home_z, self._home_r,
                    isQueued=0)
                logger.debug("[机械臂] 回零参数: (%s,%s,%s,%s)",
                             self._home_x, self._home_y, self._home_z, self._home_r)
                dType.SetPTPJointParams(self._api,
                    200, 200, 200, 200, 200, 200, 200, 200, isQueued=0)
                dType.SetPTPCommonParams(self._api, 100, 100, isQueued=0)
                logger.info("[机械臂] 初始化完成，就绪")
                return True
            else:
                logger.error("[机械臂] 连接失败，返回码: %s", state)
                return False
        except Exception as e:
            logger.error("[机械臂] 连接异常: %s", e, exc_info=True)
            return False

    # ------------------------------------------------------------------
    # 单次分拣流程（两步：拍摄识别 → 确认后分拣）
    # ------------------------------------------------------------------
    def capture_and_identify(self, callback=None):
        """第一步：拍摄照片并识别物料。

        Args:
            callback: 回调函数 callback(message: str) 用于状态通知

        Returns:
            tuple: (results, annotated_img)
        """
        def _notify(msg):
            if callback:
                callback(msg)

        # 确保相机就绪
        if not self._camera_ready:
            _notify("正在连接相机，请稍候...")
            if not self.ensure_camera():
                _notify("相机连接失败，无法拍摄")
                return [], None
            _notify("相机连接成功")

        # 拍摄
        _notify("正在拍摄...")
        img = self.camera.grab_frame()
        if img is None:
            _notify("拍摄失败：无法获取图像")
            return [], None

        _notify(f"拍摄成功: {img.shape[1]}x{img.shape[0]}")

        # 识别（现在返回 results 和 saver）
        item_name = {"cap": "瓶盖", "fruit": "水果"}.get(self._mode_name, "PCB板")
        _notify(f"正在识别{item_name}...")

        # 将标定的 pixels_per_mm 注入到检测配置中
        detect_config = self._detect_config.copy()
        detect_config["pixels_per_mm"] = self.calibrator.pixels_per_mm

        results, saver = self._detect_func(img, self.calibrator, detect_config)

        # 生成标注图像
        annotated = self._draw_func(img, results)

        if not results:
            _notify(f"未检测到{item_name}")
            return results, annotated

        _notify(f"检测到 {len(results)} 个{item_name}，请确认后点击按钮开始分拣")

        for item in results:
            _notify(item["display"])

        return results, annotated

    def execute_sort(self, results, callback=None):
        """第二步：根据识别结果控制机械臂分拣。

        Args:
            results: capture_and_identify() 返回的物料信息列表
            callback: 回调函数 callback(message: str) 用于状态通知
        """
        def _notify(msg):
            if callback:
                callback(msg)

        if not results:
            logger.info("[分拣] 无分拣目标")
            _notify("无分拣目标")
            return

        logger.info("[分拣] 待分拣数量: %d", len(results))

        # 确保机械臂就绪
        if not self._robot_ready:
            logger.info("[分拣] 机械臂未就绪，尝试连接...")
            _notify("正在连接机械臂，请稍候...")
            if not self.ensure_robot():
                logger.warning("[分拣] 机械臂连接失败，将使用模拟模式")
                _notify("机械臂连接失败，将使用模拟模式")
            else:
                _notify("机械臂连接成功")

        _notify("开始执行分拣...")

        for i, item in enumerate(results):
            logger.info("[分拣] --- 第 %d/%d 个 ---", i + 1, len(results))
            _notify(item["display"])

            phys_pos = item.get("phys_pos")
            target = self._sort_mode.get_target(item)
            grab_z = self._sort_mode.grab_z
            safe_height = self._sort_mode.safe_height

            logger.info("[分拣] phys_pos=%s, target=(%s,%s,%s,r=%s)",
                         phys_pos, target["x"], target["y"], target["z"], target.get("r", 0))

            if self._robot_connected and phys_pos is not None:
                logger.info("[分拣] 模式: 有标定坐标，移动到物料位置抓取")
                self._move_and_sort(phys_pos[0], phys_pos[1], target, grab_z, safe_height)
                _notify(f"已运送至目标({target['x']},{target['y']},{target['z']}) 旋转{target.get('r',0):.1f}°")
            elif self._robot_connected:
                logger.info("[分拣] 模式: 无标定坐标，直接到目标位置抓取")
                self._move_and_sort(target["x"], target["y"], target, grab_z, safe_height)
                _notify(f"已运送至目标({target['x']},{target['y']},{target['z']}) 旋转{target.get('r',0):.1f}°")
            else:
                logger.warning("[分拣] 机械臂未连接，模拟分拣")
                _notify(f"[模拟] 分拣 → 目标({target['x']},{target['y']},{target['z']})")

    def sort_once(self, callback=None):
        """兼容旧接口：一次完成拍摄→识别→分拣。"""
        results, _annotated = self.capture_and_identify(callback)
        self.execute_sort(results, callback)
        return results

    # ------------------------------------------------------------------
    # 回零
    # ------------------------------------------------------------------
    def go_home(self, callback=None):
        """控制机械臂回零。

        Args:
            callback: 回调函数 callback(message: str) 用于状态通知

        Returns:
            bool: 成功返回 True
        """
        def _notify(msg):
            if callback:
                callback(msg)

        if not self._robot_ready:
            _notify("正在连接机械臂，请稍候...")
            if not self.ensure_robot():
                _notify("机械臂连接失败，无法回零")
                return False
            _notify("机械臂连接成功")

        try:
            api = self._api
            logger.info("[机械臂] 开始回零 → (%s,%s,%s,%s)",
                        self._home_x, self._home_y, self._home_z, self._home_r)
            # 清空队列
            dType.SetQueuedCmdClear(api)
            # 更新回零参数
            dType.SetHOMEParams(api,
                self._home_x, self._home_y, self._home_z, self._home_r,
                isQueued=1)
            # 执行回零
            lastIndex = dType.SetHOMECmd(api, temp=0, isQueued=1)[0]
            # 开始执行队列
            dType.SetQueuedCmdStartExec(api)
            # 等待回零完成
            while lastIndex > dType.GetQueuedCmdCurrentIndex(api)[0]:
                dType.dSleep(100)
            dType.SetQueuedCmdStopExec(api)
            logger.info("[机械臂] 回零完成")
            _notify(f"回零完成 → ({self._home_x},{self._home_y},{self._home_z},{self._home_r})")
            return True
        except Exception as e:
            logger.error("[机械臂] 回零异常: %s", e, exc_info=True)
            _notify(f"回零失败: {e}")
            return False

    def set_home_params(self, x, y, z, r):
        """更新回零参数（下次回零时生效）。"""
        self._home_x = x
        self._home_y = y
        self._home_z = z
        self._home_r = r

    # ------------------------------------------------------------------
    # 清除警报
    # ------------------------------------------------------------------
    def clear_alarm(self, callback=None):
        """清除机械臂警报状态。

        Args:
            callback: 回调函数 callback(message: str) 用于状态通知

        Returns:
            bool: 成功返回 True
        """
        def _notify(msg):
            if callback:
                callback(msg)

        if not self._robot_ready:
            _notify("正在连接机械臂，请稍候...")
            if not self.ensure_robot():
                _notify("机械臂连接失败，无法清除警报")
                return False
            _notify("机械臂连接成功")

        try:
            api = self._api

            # 查询当前警报状态
            alarm_data, alarm_len = dType.GetAlarmsState(api)
            if alarm_len > 0:
                logger.warning("检测到 %d 条警报，正在清除...", alarm_len)
                _notify(f"检测到 {alarm_len} 条警报，正在清除...")
            else:
                logger.info("当前无警报")
                _notify("当前无警报")
                return True

            # 清除所有警报
            ret = dType.ClearAllAlarmsState(api)
            if ret == 0:
                logger.info("警报清除成功")
                _notify("警报清除成功")
                return True
            else:
                logger.error("警报清除失败: 返回码 %s", ret)
                _notify(f"警报清除失败: 返回码 {ret}")
                return False

        except Exception as e:
            logger.error("清除警报异常: %s", e)
            _notify(f"清除警报异常: {e}")
            return False

    # ------------------------------------------------------------------
    # 急停
    # ------------------------------------------------------------------
    def emergency_stop(self, callback=None):
        """立即停止机械臂所有运动。

        Args:
            callback: 回调函数 callback(message: str) 用于状态通知

        Returns:
            bool: 成功返回 True
        """
        def _notify(msg):
            if callback:
                callback(msg)

        logger.warning("[机械臂] === 急停触发 ===")
        _notify("急停触发，正在停止所有运动...")

        # 先停止持续分拣循环
        self.stop_continuous_sorting()

        if not self._robot_ready:
            logger.warning("[机械臂] 机械臂未连接，无法急停")
            _notify("机械臂未连接")
            return False

        try:
            api = self._api
            # 关闭吸盘
            dType.SetEndEffectorSuctionCup(api, True, False, isQueued=0)
            logger.info("[机械臂] 吸盘已关闭")
            logger.info("[机械臂] 急停完成")
            _notify("急停完成，吸盘已关闭")
            return True
        except Exception as e:
            logger.error("[机械臂] 急停异常: %s", e, exc_info=True)
            _notify(f"急停异常: {e}")
            return False

    def _move_and_sort(self, grab_x, grab_y, target, grab_z, safe_height):
        """移动到物料位置抓取，然后放到目标位置。

        使用队列模式(isQueued=1)，所有命令排队执行，避免运动和吸盘命令冲突。
        target 中的 r 字段控制末端旋转角度（rHead）。
        """
        api = self._api
        r_head = target.get("r", 0)

        logger.info("[机械臂] === 开始分拣流程 ===")
        logger.info("[机械臂] 物料位置: (%s,%s), 目标: (%s,%s,%s), 旋转: %.1f°",
                     grab_x, grab_y, target["x"], target["y"], target["z"], r_head)
        logger.info("[机械臂] 抓取高度: %s, 安全高度: %s", grab_z, safe_height)

        # 清空队列
        dType.SetQueuedCmdClear(api)

        # 1. 移动到物料上方（带旋转）
        logger.debug("[机械臂] 1/8 移动到物料上方 (%s,%s,%s,r=%.1f)", grab_x, grab_y, safe_height, r_head)
        dType.SetPTPCmd(api, dType.PTPMode.PTPMOVLXYZMode,
                        grab_x, grab_y, safe_height, r_head, isQueued=1)
        # 2. 下降到抓取高度
        logger.debug("[机械臂] 2/8 下降到抓取高度 (%s,%s,%s)", grab_x, grab_y, grab_z)
        dType.SetPTPCmd(api, dType.PTPMode.PTPMOVLXYZMode,
                        grab_x, grab_y, grab_z, r_head, isQueued=1)
        # 3. 吸盘开启
        logger.debug("[机械臂] 3/8 吸盘开启")
        lastIndex = dType.SetEndEffectorSuctionCup(api, True, True, isQueued=1)[0]
        # 4. 抬起
        logger.debug("[机械臂] 4/8 吸取后抬起 (%s,%s,%s)", grab_x, grab_y, safe_height)
        lastIndex = dType.SetPTPCmd(api, dType.PTPMode.PTPMOVLXYZMode,
                        grab_x, grab_y, safe_height, r_head, isQueued=1)[0]
        # 5. 移动到目标上方
        logger.debug("[机械臂] 5/8 移动到目标上方 (%s,%s,%s)", target["x"], target["y"], safe_height)
        lastIndex = dType.SetPTPCmd(api, dType.PTPMode.PTPMOVLXYZMode,
                        target["x"], target["y"], safe_height, r_head, isQueued=1)[0]
        # 6. 下降到目标位置
        logger.debug("[机械臂] 6/8 下降到目标位置 (%s,%s,%s)", target["x"], target["y"], target["z"])
        lastIndex = dType.SetPTPCmd(api, dType.PTPMode.PTPMOVLXYZMode,
                        target["x"], target["y"], target["z"], r_head, isQueued=1)[0]
        # 7. 吸盘释放
        logger.debug("[机械臂] 7/8 吸盘释放")
        lastIndex = dType.SetEndEffectorSuctionCup(api, True, False, isQueued=1)[0]
        # 8. 抬起
        logger.debug("[机械臂] 8/8 释放后抬起 (%s,%s,%s)", target["x"], target["y"], safe_height)
        lastIndex = dType.SetPTPCmd(api, dType.PTPMode.PTPMOVLXYZMode,
                        target["x"], target["y"], safe_height, r_head, isQueued=1)[0]

        # 开始执行队列
        dType.SetQueuedCmdStartExec(api)

        # 等待最后一个命令执行完成
        while lastIndex > dType.GetQueuedCmdCurrentIndex(api)[0]:
            dType.dSleep(100)

        # 停止队列执行
        dType.SetQueuedCmdStopExec(api)

        logger.info("[机械臂] === 分拣流程完成 ===")

    def _move_to_target(self, target):
        """仅移动到目标位置（无抓取）。"""
        api = self._api
        logger.info("[机械臂] 移动到目标位置 (%s,%s,%s)", target["x"], target["y"], target["z"])
        dType.SetQueuedCmdClear(api)
        lastIndex = dType.SetPTPCmd(api, dType.PTPMode.PTPMOVLXYZMode,
                        target["x"], target["y"], target["z"], 0, isQueued=1)[0]
        dType.SetQueuedCmdStartExec(api)
        while lastIndex > dType.GetQueuedCmdCurrentIndex(api)[0]:
            dType.dSleep(100)
        dType.SetQueuedCmdStopExec(api)
        logger.info("[机械臂] 到达目标位置")

    # ------------------------------------------------------------------
    # 持续分拣（后台线程）
    # ------------------------------------------------------------------
    def start_continuous_sorting(self, callback=None, interval=2.0):
        """启动持续分拣线程。"""
        if self._running:
            logger.warning("[分拣] 持续分拣已在运行中")
            return
        self._running = True
        logger.info("[分拣] 启动持续分拣，间隔 %.1f 秒", interval)
        self._thread = threading.Thread(
            target=self._sorting_loop,
            args=(callback, interval),
            daemon=True,
        )
        self._thread.start()

    def stop_continuous_sorting(self):
        """停止持续分拣。"""
        if self._running:
            logger.info("[分拣] 正在停止持续分拣...")
            self._running = False
            if self._thread:
                self._thread.join(timeout=5)
                self._thread = None
            logger.info("[分拣] 持续分拣已停止")

    def _sorting_loop(self, callback, interval):
        loop_count = 0
        while self._running:
            loop_count += 1
            logger.info("[分拣] ===== 循环第 %d 轮 =====", loop_count)
            self.sort_once(callback)
            if self._running:
                logger.debug("[分拣] 等待 %.1f 秒后开始下一轮...", interval)
                time.sleep(interval)
        logger.info("[分拣] 循环结束，共执行 %d 轮", loop_count)

    # ------------------------------------------------------------------
    # 资源释放
    # ------------------------------------------------------------------
    def shutdown(self):
        """释放所有资源。"""
        logger.info("[系统] 正在关闭...")
        self.stop_continuous_sorting()
        self.camera.close()
        if self._api and self._robot_connected:
            try:
                logger.info("[机械臂] 正在断开连接...")
                # 关闭吸盘
                try:
                    dType.SetEndEffectorSuctionCup(self._api, True, False, isQueued=0)
                except Exception:
                    pass
                # 停止队列执行
                try:
                    dType.SetQueuedCmdStopExec(self._api)
                except Exception:
                    pass
                # 断开连接，释放串口
                dType.DisconnectDobot(self._api)
                logger.info("[机械臂] 已断开连接，串口已释放")
            except Exception as e:
                logger.error("[机械臂] 断开连接异常: %s", e)
            self._api = None
            self._robot_connected = False
        logger.info("[系统] 已关闭")

    def __del__(self):
        self.shutdown()
