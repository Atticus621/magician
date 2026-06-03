# -- coding: utf-8 --
"""瓶盖检测模块 —— 圆形瓶盖检测、生产日期OCR、有效期判断。

功能:
  1. detect_caps(): 检测圆形瓶盖（HoughCircles）
  2. read_expiry_date(): OCR读取瓶盖上的日期文字
  3. check_expiry(): 判断是否过期
  4. process_cap_frame(): 综合处理一帧图像
"""
import sys
import os
import re
import json
import logging
from datetime import datetime

import math
import cv2
import numpy as np

_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _root not in sys.path:
    sys.path.insert(0, _root)

from modules.image_saver import ImageSaver

logger = logging.getLogger(__name__)

# 确保logger有handler（避免日志丢失）
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s'))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

# ======================================================================
# 百度OCR API
# ======================================================================
import requests as _requests
import base64 as _base64
import time as _time

_BAIDU_TOKEN = None
_BAIDU_TOKEN_EXPIRE = 0


def _get_baidu_config():
    """从 config.json 读取百度OCR配置。"""
    try:
        config_path = os.path.join(_root, "config.json")
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        baidu = cfg.get("bottle_cap", {}).get("baidu_ocr", {})
        return baidu.get("api_key", ""), baidu.get("secret_key", "")
    except Exception as e:
        logger.error("读取百度OCR配置失败: %s", e)
        return "", ""


def _get_baidu_token():
    """获取百度API的access_token（带缓存）。"""
    global _BAIDU_TOKEN, _BAIDU_TOKEN_EXPIRE

    if _BAIDU_TOKEN and _time.time() < _BAIDU_TOKEN_EXPIRE:
        return _BAIDU_TOKEN

    api_key, secret_key = _get_baidu_config()
    if not api_key or not secret_key:
        logger.error("百度OCR API Key未配置")
        return None

    url = "https://aip.baidubce.com/oauth/2.0/token"
    params = {
        "grant_type": "client_credentials",
        "client_id": api_key,
        "client_secret": secret_key,
    }
    try:
        resp = _requests.post(url, params=params, timeout=10)
        data = resp.json()
        token = data.get("access_token")
        if token:
            _BAIDU_TOKEN = token
            # 提前5分钟过期，避免边界问题
            _BAIDU_TOKEN_EXPIRE = _time.time() + data.get("expires_in", 2592000) - 300
            logger.info("百度OCR access_token 获取成功")
        else:
            logger.error("百度OCR token获取失败: %s", data)
        return token
    except Exception as e:
        logger.error("百度OCR token请求异常: %s", e)
        return None


def _baidu_ocr(image_base64):
    """调用百度高精度文字识别接口（瓶盖圆弧文字优化）。

    使用 accurate_basic 接口，开启圆弧/环形文字增强、
    单字符识别粒度、方向检测等参数，提高瓶盖日期识别率。

    Args:
        image_base64: 图片的base64编码字符串

    Returns:
        list[str]: 识别到的文字行列表，失败返回空列表
    """
    token = _get_baidu_token()
    if not token:
        return []

    url = f"https://aip.baidubce.com/rest/2.0/ocr/v1/accurate_basic?access_token={token}"
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    data = {
        "image": image_base64,
        "language_type": "ENG",              # 纯字母+数字+符号优先，不漏大写、:/
        "detect_direction": "true",          # 自动检测文字旋转角度
        "enable_unified_vertical": "true",   # 弧形、环形、不规则文字增强
        "recognize_granularity": "small",    # 按单字符识别，圆弧分散字母不会漏掉
    }

    try:
        resp = _requests.post(url, headers=headers, data=data, timeout=10)
        result = resp.json()
        if "words_result" in result:
            return [item["words"] for item in result["words_result"]]
        else:
            logger.warning("百度OCR返回异常: %s", result)
            return []
    except Exception as e:
        logger.error("百度OCR请求失败: %s", e)
        return []


HAS_OCR = True  # OCR始终可用（只要配置了key）


# ======================================================================
# 圆环展开（极坐标变换）
# ======================================================================
def _find_longest_white_block(gray, cx, cy, r, ratio=0.6, samples=360):
    """采样各角度的圆环亮度，找到最长连续白色区段的中心作为起始角度。

    在圆环中间半径处采样一圈像素，按阈值二值化后找最长连续高亮段，
    返回其中心角度。这样文字（暗色）会被完整聚集，不会分散在左右两端。

    Args:
        gray: 灰度图
        cx, cy: 圆心坐标
        r: 圆半径
        ratio: 圆环内径比例
        samples: 采样角度数

    Returns:
        float: 最佳起始角度（弧度）
    """
    r_inner = int(r * ratio)
    r_mid = (r + r_inner) // 2

    brightness = []
    for i in range(samples):
        angle = 2.0 * math.pi * i / samples
        vals = []
        for dr in range(-3, 4):
            px = int(cx + (r_mid + dr) * math.cos(angle))
            py = int(cy + (r_mid + dr) * math.sin(angle))
            if 0 <= px < gray.shape[1] and 0 <= py < gray.shape[0]:
                vals.append(int(gray[py, px]))
        brightness.append(np.mean(vals) if vals else 0)

    threshold = np.mean(brightness)
    is_white = [b > threshold for b in brightness]

    best_start, best_len = 0, 0
    cur_start, cur_len = -1, 0

    for i in range(samples * 2):
        idx = i % samples
        if is_white[idx]:
            if cur_len == 0:
                cur_start = idx
            cur_len += 1
            if cur_len > best_len:
                best_len = cur_len
                best_start = cur_start
        else:
            cur_len = 0

    best_len = min(best_len, samples)
    center_idx = (best_start + best_len // 2) % samples
    best_angle = 2.0 * math.pi * center_idx / samples

    logger.info("圆环展开: 白色段=%d°, 起始角度=%d°", best_len, center_idx)
    return best_angle


def _unwrap_ring(img, cx, cy, r, ratio=0.6, output_width=1080):
    """将圆环区域按极坐标展开为矩形，用于OCR识别。

    Args:
        img: BGR图像
        cx, cy: 圆心坐标
        r: 圆半径(px)
        ratio: 圆环内径比例（内径 = r * ratio）
        output_width: 展开后矩形的宽度（对应360°）

    Returns:
        np.ndarray: 展开后的矩形BGR图像
    """
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    start_angle = _find_longest_white_block(gray, cx, cy, r, ratio)

    r_inner = int(r * ratio)
    r_outer = r
    ring_width = r_outer - r_inner

    n_cols = output_width
    n_rows = ring_width

    map_x = np.zeros((n_rows, n_cols), dtype=np.float32)
    map_y = np.zeros((n_rows, n_cols), dtype=np.float32)

    for col in range(n_cols):
        angle = start_angle + 2.0 * math.pi * col / n_cols
        cos_a = math.cos(angle)
        sin_a = math.sin(angle)

        for row in range(n_rows):
            radius = r_outer - row
            map_x[row, col] = cx + radius * cos_a
            map_y[row, col] = cy + radius * sin_a

    unwrapped = cv2.remap(img, map_x, map_y, cv2.INTER_LINEAR,
                          borderMode=cv2.BORDER_WRAP)
    return unwrapped


# ======================================================================
# 瓶盖检测（HoughCircles）
# ======================================================================
def detect_caps(img, diameter_min_mm=27, diameter_max_mm=33,
                pixels_per_mm=10.0, min_dist_ratio=1.5, saver=None):
    """检测图像中的圆形瓶盖。

    使用 HoughCircles 检测圆形，按直径范围过滤。

    Args:
        img: BGR图像
        diameter_min_mm: 瓶盖最小直径(mm)
        diameter_max_mm: 瓶盖最大直径(mm)
        pixels_per_mm: 像素/毫米比例
        min_dist_ratio: 圆心最小距离比例（相对于直径）
        saver: ImageSaver实例，用于保存中间图像

    Returns:
        list[dict]: 每个瓶盖的信息 {center, radius, diameter_mm, bbox}
    """
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    if saver:
        saver.save(gray, "灰度图")

    blurred = cv2.GaussianBlur(gray, (9, 9), 2)
    if saver:
        saver.save(blurred, "高斯模糊")

    # 直径范围转像素
    r_min = int(diameter_min_mm * pixels_per_mm / 2)
    r_max = int(diameter_max_mm * pixels_per_mm / 2)
    min_dist = int(r_min * min_dist_ratio * 2)

    # HoughCircles 检测
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

        # 过滤直径范围
        if diameter_mm < diameter_min_mm or diameter_mm > diameter_max_mm:
            continue

        # 计算边界框（用于OCR区域）
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
# OCR读取日期
# ======================================================================
def read_expiry_date(img, roi=None):
    """从瓶盖图像中OCR读取日期文字（百度OCR）。

    Args:
        img: BGR图像（原图或瓶盖ROI）
        roi: (x, y, w, h) 感兴趣区域，None则使用整张图

    Returns:
        str: 识别到的文字，失败返回空字符串
    """
    if not HAS_OCR:
        return ""

    if roi is not None:
        x, y, w, h = roi
        region = img[y:y+h, x:x+w]
    else:
        region = img

    if region.size == 0:
        return ""

    try:
        # 图片编码为base64
        _, buf = cv2.imencode('.png', region)
        image_base64 = _base64.b64encode(buf).decode("utf-8")

        texts = _baidu_ocr(image_base64)

        if not texts:
            logger.info("OCR未识别到任何文字")
            return ""

        full_text = " ".join(texts)
        logger.info("OCR识别结果: %s", full_text)

        return full_text
    except Exception as e:
        logger.error("OCR识别失败: %s", e)
        return ""


# ======================================================================
# 日期解析与判断
# ======================================================================
def parse_expiry_date(text, template="Expiry:*/*/*"):
    """从OCR文字中解析日期。

    匹配任意 YYYY/MM/DD、YYYY-MM-DD、YYYY.MM.DD 格式的日期，
    不要求 "Expiry" 前缀完整。

    Args:
        text: OCR识别的文字
        template: 日期模板（保留兼容，实际不用于严格匹配）

    Returns:
        datetime: 解析到的日期，失败返回 None
    """
    if not text:
        return None

    # 匹配常见日期分隔符：/ - .
    pattern = r'(\d{4})[/.-](\d{1,2})[/.-](\d{1,2})'
    match = re.search(pattern, text)

    if not match:
        return None

    try:
        year = int(match.group(1))
        month = int(match.group(2))
        day = int(match.group(3))
        return datetime(year, month, day)
    except ValueError:
        return None


def check_expiry(date, expiry_date_str):
    """判断日期是否超过有效期。

    Args:
        date: datetime 对象（瓶盖上的日期）
        expiry_date_str: 有效期字符串，如 "2026/6/15"

    Returns:
        tuple: (is_valid, status, message)
            is_valid: True=在有效期内(OK), False=已过期(NG)
            status: "OK" 或 "NG"
            message: 说明文字
    """
    if date is None:
        return False, "NG", "无法识别日期"

    try:
        parts = expiry_date_str.split("/")
        expiry = datetime(int(parts[0]), int(parts[1]), int(parts[2]))
    except (ValueError, IndexError):
        return False, "NG", f"有效期配置错误: {expiry_date_str}"

    date_str = f"{date.year}/{date.month}/{date.day}"
    if date <= expiry:
        return True, "OK", f"日期{date_str}在有效期内"
    else:
        return False, "NG", f"日期{date_str}已超过有效期{expiry_date_str}"


# ======================================================================
# 绘制检测结果
# ======================================================================
def draw_cap_results(img, results):
    """在图像上绘制瓶盖检测结果。

    每个瓶盖显示：编号、直径、OCR原文、解析日期、OK/NG状态。

    Args:
        img: 原始BGR图像（会复制一份）
        results: process_cap_frame() 返回的结果列表

    Returns:
        annotated: 标注后的BGR图像
    """
    annotated = img.copy()

    for i, item in enumerate(results):
        cx, cy = item["center"]
        r = item["radius"]
        status = item["status"]

        # 圆形检测框（绿色=OK，红色=NG）
        color = (0, 255, 0) if status == "OK" else (0, 0, 255)
        cv2.circle(annotated, (cx, cy), r, color, 2)

        # 瓶盖中心大号 OK/NG 标记
        text_size = cv2.getTextSize(status, cv2.FONT_HERSHEY_SIMPLEX, 1.0, 2)[0]
        cv2.putText(annotated, status,
                    (cx - text_size[0] // 2, cy + text_size[1] // 2),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, color, 2)

        # 多行标签（圆框上方）
        date = item.get("date")
        date_str = date.strftime("%Y/%m/%d") if date else "N/A"
        ocr_text = item.get("date_text", "") or "(empty)"

        label1 = f"#{i+1} d={item['diameter_mm']}mm"
        label2 = f"OCR: {ocr_text[:25]}"
        label3 = f"Date: {date_str}"

        y0 = cy - r - 38
        cv2.putText(annotated, label1, (cx - r, y0),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
        cv2.putText(annotated, label2, (cx - r, y0 + 16),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 0), 1)
        cv2.putText(annotated, label3, (cx - r, y0 + 32),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 200, 255), 1)

    return annotated


# ======================================================================
# 综合处理：检测瓶盖 → OCR → 判断有效期
# ======================================================================
def process_cap_frame(img, calibrator=None, cap_config=None):
    """处理单帧图像，返回瓶盖检测结果。

    Args:
        img: BGR图像
        calibrator: Calibrator对象（坐标转换用）
        cap_config: dict，瓶盖配置参数

    Returns:
        list[dict]: 每个瓶盖的信息 {
            "center": (cx, cy),
            "radius": int,
            "diameter_mm": float,
            "bbox": (x, y, w, h),
            "phys_pos": (x, y) | None,
            "date": datetime | None,
            "date_text": str,
            "status": "OK" | "NG",
            "display": str,
        }
    """
    config = cap_config or {}
    diameter_min = config.get("diameter_min_mm", 27)
    diameter_max = config.get("diameter_max_mm", 33)
    pixels_per_mm = config.get("pixels_per_mm", 10.0)
    expiry_date = config.get("expiry_date", "2026/6/15")
    template = config.get("date_template", "Expiry:*/*/*")

    # 创建图像保存器
    saver = ImageSaver("cap")
    saver.save(img, "原始图像")

    # 检测圆形瓶盖
    caps = detect_caps(img, diameter_min, diameter_max, pixels_per_mm, saver=saver)

    results = []
    for cap in caps:
        cx, cy = cap["center"]
        r = cap["radius"]
        bbox = cap["bbox"]

        # 圆环展开后再OCR（将环形文字拉直为矩形）
        unwrapped = _unwrap_ring(img, cx, cy, r, ratio=0.6, output_width=1080)
        if saver:
            saver.save(unwrapped, f"瓶盖_({cx},{cy})_展开")

        date_text = read_expiry_date(unwrapped)
        date = parse_expiry_date(date_text, template)

        # 判断有效期
        is_valid, status, _message = check_expiry(date, expiry_date)

        # 坐标转换
        phys_pos = None
        if calibrator is not None and calibrator.is_calibrated:
            phys_pos = calibrator.img_to_phys((cx, cy))

        # 显示文字（含OCR原文）
        ocr_hint = f" [{date_text[:20]}]" if date_text else ""
        pos_str = f"({phys_pos[0]:.0f},{phys_pos[1]:.0f})" if phys_pos else "未标定"
        display = f"(瓶盖) {cap['diameter_mm']}mm{ocr_hint},检测结果：{status}, 位置：{pos_str}"

        results.append({
            "center": (cx, cy),
            "radius": cap["radius"],
            "diameter_mm": cap["diameter_mm"],
            "bbox": bbox,
            "phys_pos": phys_pos,
            "date": date,
            "date_text": date_text,
            "status": status,
            "display": display,
        })

    # 保存最终标注图
    annotated = draw_cap_results(img, results)
    if saver:
        saver.save(annotated, "最终标注结果")

    return results, saver
