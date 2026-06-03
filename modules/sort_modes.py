# -- coding: utf-8 --
"""分拣模式模块 —— 定义不同的分拣目标选择策略。

两种模式：
  1. SimpleSortMode: 单一目标区域（PCB板）
  2. DualAreaSortMode: OK/NG双区域（瓶盖）
"""
import logging

logger = logging.getLogger(__name__)

# 确保logger有handler
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s'))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


class SimpleSortMode:
    """单一目标区域模式（适用于PCB板）。

    所有物料都分拣到同一个目标位置。
    """

    def __init__(self, config):
        """
        Args:
            config: dict，包含 sort_target, grab_z, safe_height
        """
        self.target = config.get("sort_target", {"x": 200, "y": 110, "z": 20})
        self.grab_z = config.get("grab_z", -30)
        self.safe_height = config.get("safe_height", 50)

    def get_target(self, item):
        """获取分拣目标位置。

        Args:
            item: 检测结果字典（包含 status, r_angle 等字段）

        Returns:
            dict: {"x": ..., "y": ..., "z": ..., "r": ...}
        """
        target = dict(self.target)
        target["r"] = item.get("r_angle", 0)
        return target

    @property
    def mode_name(self):
        return "simple"


class DualAreaSortMode:
    """OK/NG双区域模式（适用于瓶盖）。

    根据检测结果的 status 字段，分拣到不同的目标区域。
    """

    def __init__(self, config):
        """
        Args:
            config: dict，包含 ok_target, ng_target, grab_z, safe_height
        """
        self.ok_target = config.get("ok_target", {"x": 250, "y": 110, "z": 20})
        self.ng_target = config.get("ng_target", {"x": 250, "y": -110, "z": 20})
        self.grab_z = config.get("grab_z", -25)
        self.safe_height = config.get("safe_height", 50)

    def get_target(self, item):
        """根据检测结果状态获取分拣目标位置。

        Args:
            item: 检测结果字典（必须包含 status 字段）

        Returns:
            dict: {"x": ..., "y": ..., "z": ..., "r": ...}
        """
        status = item.get("status", "OK")
        if status == "OK":
            target = dict(self.ok_target)
        else:
            target = dict(self.ng_target)
        target["r"] = item.get("r_angle", 0)
        return target

    @property
    def mode_name(self):
        return "dual_area"


def create_sort_mode(mode_name, config):
    """工厂函数：根据模式名称创建对应的分拣模式实例。

    Args:
        mode_name: "simple" 或 "dual_area"
        config: 分拣配置参数

    Returns:
        SimpleSortMode 或 DualAreaSortMode 实例
    """
    if mode_name == "dual_area":
        logger.info("创建双区域分拣模式")
        return DualAreaSortMode(config)
    else:
        logger.info("创建单目标分拣模式")
        return SimpleSortMode(config)
