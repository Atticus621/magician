# -- coding: utf-8 --
"""水果检测模块 —— 圆形水果检测、YOLO分类识别。

功能:
  1. detect_fruits(): 检测圆形水果（HoughCircles）
  2. classify_fruit(): YOLO模型分类水果种类
  3. process_fruit_frame(): 综合处理一帧图像
  4. draw_fruit_results(): 绘制检测结果

流程: HoughCircles检测圆形 → 裁剪圆形区域 → YOLO分类 → 返回结果
"""
import sys
import os
import logging

import cv2
import numpy as np

_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _root not in sys.path:
    sys.path.insert(0, _root)

from modules.image_saver import ImageSaver
from modules.config_manager import config as app_config

logger = logging.getLogger(__name__)

# 确保logger有handler
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s'))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

# ======================================================================
# YOLO 分类模型（延迟加载）
# best.pt: 苹果/香蕉分类模型
# ======================================================================
_yolo_model = None
_yolo_loaded = False


def _get_yolo_model():
    """延迟加载 YOLO 分类模型。"""
    global _yolo_model, _yolo_loaded

    if _yolo_loaded:
        return _yolo_model

    try:
        from ultralytics import YOLO

        path = os.path.join(_root, "models", "best.pt")
        if os.path.exists(path):
            _yolo_model = YOLO(path)
            logger.info("YOLO模型加载成功: %s", path)
        else:
            logger.error("模型文件不存在: %s", path)

        _yolo_loaded = True
        return _yolo_model

    except ImportError:
        _yolo_loaded = True
        logger.error("ultralytics 未安装，请运行: pip install ultralytics")
        return None
    except Exception as e:
        _yolo_loaded = True
        logger.error("YOLO模型加载失败: %s", e)
        return None


def preload_yolo_model():
    """预加载 YOLO 模型，在系统初始化时调用。"""
    return _get_yolo_model()


# ======================================================================
# 圆形水果检测
# ======================================================================
def detect_fruits(img, diameter_min_mm=40, diameter_max_mm=120,
                  pixels_per_mm=10.0, min_dist_ratio=1.5, saver=None):
    """检测图像中的圆形水果。

    使用 HoughCircles 检测圆形，按直径范围过滤。
    参数与瓶盖检测保持一致。

    Args:
        img: BGR图像
        diameter_min_mm: 水果最小直径(mm)
        diameter_max_mm: 水果最大直径(mm)
        pixels_per_mm: 像素/毫米比例
        min_dist_ratio: 圆心最小距离比例
        saver: ImageSaver实例

    Returns:
        list[dict]: 每个水果的信息 {center, radius, diameter_mm, bbox}
    """
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    if saver:
        saver.save(gray, "灰度图")

    blurred = cv2.GaussianBlur(gray, (9, 9), 2)
    if saver:
        saver.save(blurred, "高斯模糊")

    r_min = int(diameter_min_mm * pixels_per_mm / 2)
    r_max = int(diameter_max_mm * pixels_per_mm / 2)
    min_dist = int(r_min * min_dist_ratio * 2)

    circles = cv2.HoughCircles(
        blurred,
        cv2.HOUGH_GRADIENT,
        dp=1.2,
        minDist=max(min_dist, 20),
        param1=100,
        param2=50,
        minRadius=r_min,
        maxRadius=r_max,
    )

    if circles is None:
        return []

    circles = np.uint16(np.around(circles))
    results = []

    for c in circles[0]:
        cx, cy, r = int(c[0]), int(c[1]), int(c[2])
        diameter_mm = (r * 2) / pixels_per_mm

        if diameter_mm < diameter_min_mm or diameter_mm > diameter_max_mm:
            continue

        # 边界框（用于裁剪ROI）
        margin = int(r * 0.3)
        x1 = max(0, cx - r - margin)
        y1 = max(0, cy - r - margin)
        x2 = min(img.shape[1], cx + r + margin)
        y2 = min(img.shape[0], cy + r + margin)

        results.append({
            "center": (cx, cy),
            "radius": r,
            "diameter_mm": round(diameter_mm, 1),
            "bbox": (x1, y1, x2 - x1, y2 - y1),
        })

    return results


# ======================================================================
# YOLO 水果分类
# ======================================================================
def classify_fruit(img, roi=None, confidence_threshold=0.3):
    """使用 best.pt 模型识别水果种类。

    Args:
        img: BGR图像
        roi: (x, y, w, h) 感兴趣区域
        confidence_threshold: 置信度阈值

    Returns:
        tuple: (class_name, confidence)  如 ("Apples", 0.95)
               失败返回 (None, 0.0)
    """
    model = _get_yolo_model()
    if model is None:
        return None, 0.0

    if roi is not None:
        x, y, w, h = roi
        region = img[y:y+h, x:x+w]
    else:
        region = img

    if region.size == 0:
        return None, 0.0

    try:
        r = model(region, verbose=False)
        pred = model.names[r[0].probs.top1]
        conf = r[0].probs.top1conf.item()

        if conf < confidence_threshold:
            return None, conf

        # class name 首字母大写，保持格式一致
        pred = pred.capitalize() if pred else None
        return pred, conf

    except Exception as e:
        logger.error("YOLO分类失败: %s", e)
        return None, 0.0


# ======================================================================
# 绘制检测结果
# ======================================================================
def draw_fruit_results(img, results):
    """在图像上绘制水果检测结果。

    每个水果显示：编号、直径、种类、置信度。

    Args:
        img: 原始BGR图像
        results: process_fruit_frame() 返回的结果列表

    Returns:
        annotated: 标注后的BGR图像
    """
    annotated = img.copy()

    for i, item in enumerate(results):
        cx, cy = item["center"]
        r = item["radius"]
        fruit_name = item.get("fruit_name") or "Unknown"
        confidence = item.get("confidence", 0)
        status = item.get("status", "NG")

        # OK=绿色，NG=红色
        color = (0, 255, 0) if status == "OK" else (0, 0, 255)
        cv2.circle(annotated, (cx, cy), r, color, 2)

        # 中心大号 OK/NG 标记
        text_size = cv2.getTextSize(status, cv2.FONT_HERSHEY_SIMPLEX, 1.0, 2)[0]
        cv2.putText(annotated, status,
                    (cx - text_size[0] // 2, cy + text_size[1] // 2),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, color, 2)

        # 多行标签
        label1 = f"#{i+1} d={item['diameter_mm']}mm"
        label2 = f"{fruit_name} {confidence:.0%}"

        y0 = cy - r - 22
        cv2.putText(annotated, label1, (cx - r, y0),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
        cv2.putText(annotated, label2, (cx - r, y0 + 16),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)

    return annotated


# ======================================================================
# 综合处理：检测水果 → YOLO分类
# ======================================================================
def process_fruit_frame(img, calibrator=None, fruit_config=None):
    """处理单帧图像，返回水果检测结果。

    Args:
        img: BGR图像
        calibrator: Calibrator对象
        fruit_config: dict，水果配置参数

    Returns:
        tuple: (results, saver)
            results: list[dict] 每个水果的信息 {
                "center", "radius", "diameter_mm", "bbox",
                "phys_pos", "fruit_name", "confidence",
                "status", "display",
            }
            saver: ImageSaver实例
    """
    config = fruit_config or {}
    diameter_min = config.get("diameter_min_mm", 40)
    diameter_max = config.get("diameter_max_mm", 120)
    pixels_per_mm = config.get("pixels_per_mm", 10.0)
    conf_threshold = config.get("confidence_threshold", 0.3)
    ok_fruit = config.get("ok_fruit", "Apples")

    saver = ImageSaver("fruit")
    saver.save(img, "原始图像")

    # 检测圆形
    fruits = detect_fruits(img, diameter_min, diameter_max, pixels_per_mm, saver=saver)

    results = []
    for i, fruit in enumerate(fruits):
        cx, cy = fruit["center"]
        bbox = fruit["bbox"]

        # 保存裁剪的彩色ROI
        x, y, w, h = bbox
        roi_img = img[y:y+h, x:x+w]
        if roi_img.size > 0:
            saver.save(roi_img, f"水果{i+1}_裁剪")

        # YOLO分类
        fruit_name, confidence = classify_fruit(img, roi=bbox,
                                                confidence_threshold=conf_threshold)

        # 坐标转换
        phys_pos = None
        if calibrator is not None and calibrator.is_calibrated:
            phys_pos = calibrator.img_to_phys((cx, cy))

        # 只分拣苹果和香蕉，其他跳过
        if fruit_name not in (ok_fruit, "Bananas"):
            continue

        name = fruit_name
        status = "OK" if fruit_name == ok_fruit else "NG"
        pos_str = f"({phys_pos[0]:.0f},{phys_pos[1]:.0f})" if phys_pos else "未标定"
        display = f"(水果) {fruit['diameter_mm']}mm, {name} {confidence:.0%}, 检测结果：{status}, 位置：{pos_str}"

        results.append({
            "center": (cx, cy),
            "radius": fruit["radius"],
            "diameter_mm": fruit["diameter_mm"],
            "bbox": bbox,
            "phys_pos": phys_pos,
            "fruit_name": name,
            "confidence": confidence,
            "status": status,
            "display": display,
        })

    # 保存标注图
    annotated = draw_fruit_results(img, results)
    if saver:
        saver.save(annotated, "最终标注结果")

    return results, saver
