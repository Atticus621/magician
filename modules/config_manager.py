# -- coding: utf-8 --
"""配置管理模块 —— 统一加载和管理 config.json。

用法：
    from modules.config_manager import config

    # 获取标定文件路径
    xml_path = config.calibration.xml_path

    # 获取PCB配置
    ppm = config.pcb.pixels_per_mm
    size_range = config.pcb.size_range

    # 获取瓶盖配置
    cap_cfg = config.bottle_cap.diameter_range

    # 获取整个配置字典
    cfg_dict = config.get_dict()
"""
import os
import sys
import json
import logging

_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _root not in sys.path:
    sys.path.insert(0, _root)

logger = logging.getLogger(__name__)


class _ConfigSection:
    """配置节，支持属性访问。"""

    def __init__(self, data: dict):
        for key, value in data.items():
            if isinstance(value, dict):
                setattr(self, key, _ConfigSection(value))
            else:
                setattr(self, key, value)

    def get(self, key, default=None):
        """获取配置值，支持默认值。"""
        return getattr(self, key, default)

    def to_dict(self):
        """转回字典格式。"""
        result = {}
        for key, value in self.__dict__.items():
            if isinstance(value, _ConfigSection):
                result[key] = value.to_dict()
            else:
                result[key] = value
        return result


class ConfigManager:
    """配置管理器，单例模式。"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._loaded = False
        return cls._instance

    def __init__(self):
        if self._loaded:
            return
        self._loaded = True
        self._data = {}
        self._load()

    def _load(self):
        """加载配置文件。"""
        config_path = os.path.join(_root, "config.json")
        if not os.path.exists(config_path):
            logger.warning("配置文件不存在: %s", config_path)
            return

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                self._data = json.load(f)
            logger.info("已加载配置文件: %s", config_path)
        except Exception as e:
            logger.error("加载配置文件失败: %s", e)
            return

        # 创建属性访问
        for key, value in self._data.items():
            if isinstance(value, dict):
                setattr(self, key, _ConfigSection(value))
            else:
                setattr(self, key, value)

    def reload(self):
        """重新加载配置文件。"""
        self._loaded = False
        self._data = {}
        # 清除旧的属性
        for key in list(self.__dict__.keys()):
            if key not in ('_loaded', '_data'):
                delattr(self, key)
        self._load()

    def get_dict(self):
        """获取完整配置字典。"""
        return self._data.copy()

    def get(self, key, default=None):
        """获取顶级配置项。"""
        return self._data.get(key, default)


# 全局配置实例（单例）
config = ConfigManager()
