# -- coding: utf-8 --
"""图像保存工具模块 —— 用于保存检测过程中的中间图像。

所有图像保存到 picture/ 文件夹，命名格式：
  {timestamp}_{step:02d}_{description}.png

用法：
  from modules.image_saver import ImageSaver
  saver = ImageSaver("pcb")  # 或 "cap"
  saver.save(img, "原始图像")
  saver.save(gray, "灰度图")
"""
import os
import sys
import time
import cv2
import numpy as np

_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _root not in sys.path:
    sys.path.insert(0, _root)

PICTURE_DIR = os.path.join(_root, "picture")

# 中文描述到英文文件名的映射
_NAME_MAP = {
    "原始图像": "original",
    "灰度图": "gray",
    "高斯模糊": "blurred",
    "边缘检测": "edges",
    "膨胀边缘": "dilated_edges",
    "二值化": "binary",
    "形态学处理后": "morphology",
    "轮廓检测结果": "contours",
    "非黑色区域mask": "non_black_mask",
    "反光抑制后": "reflection_suppressed",
    "绿色区域mask": "green_mask",
    "绿色膨胀mask": "green_dilated_mask",
    "PCB检测mask": "pcb_mask",
    "最终标注结果": "final_annotated",
}

# 动态中文描述的前缀映射（用于水果裁剪、瓶盖展开等）
_DYNAMIC_PREFIX_MAP = {
    "水果": "fruit",
    "裁剪": "crop",
    "瓶盖": "cap",
    "展开": "unwrapped",
}


def _translate_chinese(desc):
    """将动态中文描述翻译为英文文件名。

    例: "水果7_裁剪" → "fruit7_crop"
        "瓶盖_(100,200)_展开" → "cap_(100,200)_unwrapped"
    """
    result = desc
    for zh, en in _DYNAMIC_PREFIX_MAP.items():
        result = result.replace(zh, en)
    # 如果仍有非ASCII字符，直接丢弃
    result = result.encode("ascii", "ignore").decode("ascii")
    return result if result else "img"


class ImageSaver:
    """图像保存器，用于保存检测过程中的中间图像。"""

    def __init__(self, prefix="img"):
        """
        Args:
            prefix: 文件名前缀，如 "pcb" 或 "cap"
        """
        self._prefix = prefix
        self._step = 0
        self._timestamp = time.strftime("%Y%m%d_%H%M%S")
        self._session_dir = os.path.join(PICTURE_DIR, f"{self._timestamp}_{prefix}")

        # 确保目录存在
        os.makedirs(self._session_dir, exist_ok=True)

    def save(self, img, description):
        """保存图像到picture文件夹。

        Args:
            img: BGR图像或灰度图（numpy数组）
            description: 图像描述，如 "原始图像"、"灰度图"

        Returns:
            str: 保存的文件路径
        """
        if img is None:
            return None

        self._step += 1

        # 使用英文文件名避免编码问题
        eng_name = _NAME_MAP.get(description)
        if eng_name is None:
            eng_name = _translate_chinese(description)
        filename = f"{self._step:02d}_{eng_name}.png"
        filepath = os.path.join(self._session_dir, filename)

        try:
            # 确保图像是可保存的格式
            if img.ndim == 2:
                # 单通道图像（灰度图、mask）
                save_img = img
            elif img.ndim == 3:
                # 三通道图像（BGR）
                save_img = img
            else:
                print(f"警告: 不支持的图像维度 {img.ndim}")
                return None

            cv2.imwrite(filepath, save_img)
            print(f"[ImageSaver] 保存: {filename}")
            return filepath
        except Exception as e:
            print(f"保存图像失败: {e}")
            return None

    def save_with_text(self, img, description, text_lines=None):
        """保存图像并在左上角添加文字说明。

        Args:
            img: BGR图像
            description: 图像描述
            text_lines: 要在图像上显示的文字行列表

        Returns:
            str: 保存的文件路径
        """
        if img is None:
            return None

        # 复制图像以免修改原图
        annotated = img.copy()

        # 如果是单通道图像，转换为三通道以便添加文字
        if annotated.ndim == 2:
            annotated = cv2.cvtColor(annotated, cv2.COLOR_GRAY2BGR)

        # 在图像上添加文字
        if text_lines:
            y_offset = 30
            for line in text_lines:
                cv2.putText(annotated, line, (10, y_offset),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                y_offset += 30

        return self.save(annotated, description)

    @property
    def session_dir(self):
        """当前会话的保存目录。"""
        return self._session_dir


def get_latest_session(prefix=None):
    """获取最新的保存会话目录。

    Args:
        prefix: 可选的前缀过滤

    Returns:
        str: 最新会话目录路径，无则返回 None
    """
    if not os.path.exists(PICTURE_DIR):
        return None

    dirs = os.listdir(PICTURE_DIR)
    if prefix:
        dirs = [d for d in dirs if d.endswith(f"_{prefix}")]

    if not dirs:
        return None

    dirs.sort(reverse=True)
    return os.path.join(PICTURE_DIR, dirs[0])
