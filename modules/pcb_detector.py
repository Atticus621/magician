# -- coding: utf-8 --
"""PCB板检测模块 —— 绿色PCB板检测、焊点识别。

功能:
  1. detect_pcb(): 检测绿色长方形PCB板，测量长和宽
  2. count_solder_points(): 识别PCB区域内的银白色焊点数量
  3. process_frame(): 综合处理一帧图像
  4. draw_results(): 绘制检测结果

接口与 cap_detector.py 保持一致。
"""
import sys
import os
import logging
import cv2
import numpy as np
import zxingcpp

_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _root not in sys.path:
    sys.path.insert(0, _root)

from algorithm.calibration import Calibrator
from modules.image_saver import ImageSaver

logger = logging.getLogger(__name__)

# 确保logger有handler（避免日志丢失）
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s'))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


# ======================================================================
# 预处理：抑制反光（多级策略）
# ======================================================================
def _detect_reflection_mask(img):
    """检测图像中的反光/高光区域，返回二值mask。

    反光特征：饱和度低 + 亮度高。
    """
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    s = hsv[:, :, 1]
    v = hsv[:, :, 2]

    # 宽松阈值，尽可能多地捕获反光区域
    reflection = (s < 100) & (v > 160)
    reflection = reflection.astype(np.uint8) * 255

    # 膨胀，覆盖反光边缘过渡带
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
    reflection = cv2.dilate(reflection, kernel, iterations=2)
    return reflection


def _suppress_reflection(img):
    """抑制图像中的高光/反光，恢复被冲淡的颜色。

    策略：
      1. CLAHE均衡化 → 改善局部对比度，压缩亮度动态范围
      2. 检测反光区域 → 对该区域单独压亮度、拉饱和度
      3. 反光区域用周围颜色修复(inpaint) → 为绿色检测提供干净图像

    Returns:
        corrected: 处理后的BGR图像
    """
    # --- Step 1: CLAHE 均衡化，压缩亮度动态范围 ---
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l_ch, a_ch, b_ch = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    l_clahe = clahe.apply(l_ch)
    lab_clahe = cv2.merge([l_clahe, a_ch, b_ch])
    img_clahe = cv2.cvtColor(lab_clahe, cv2.COLOR_LAB2BGR)

    # --- Step 2: 在CLAHE结果上检测反光并压平 ---
    hsv = cv2.cvtColor(img_clahe, cv2.COLOR_BGR2HSV).astype(np.float32)
    h, s, v = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]

    reflection_mask = (s < 100) & (v > 160)

    # 强力压低亮度，大幅拉高饱和度
    v[reflection_mask] = np.clip(v[reflection_mask] * 0.35, 0, 255)
    s[reflection_mask] = np.clip(s[reflection_mask] + 120, 0, 255)

    hsv[:, :, 0] = h
    hsv[:, :, 1] = s
    hsv[:, :, 2] = v
    corrected = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)

    # --- Step 3: 对严重反光区域做inpaint修复 ---
    refl_mask = _detect_reflection_mask(img)
    # 只修复高亮核心区（膨胀前的mask用原始检测）
    hsv_raw = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    core_reflection = (hsv_raw[:, :, 1] < 60) & (hsv_raw[:, :, 2] > 210)
    core_reflection = core_reflection.astype(np.uint8) * 255
    kernel_core = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    core_reflection = cv2.morphologyEx(core_reflection, cv2.MORPH_CLOSE, kernel_core)

    if np.any(core_reflection):
        corrected = cv2.inpaint(corrected, core_reflection, 10, cv2.INPAINT_TELEA)

    return corrected




# ======================================================================
# PCB板检测（最简化：直接矩形检测）
# ======================================================================
def detect_pcb(img, pcb_size_range=None, pixels_per_mm=None, min_area=800, saver=None, outline_rgb=None):
    """检测PCB板：颜色分割 + 四边形多边形检测。

    先按RGB范围做颜色分割生成二值图，再找轮廓，筛选四边形。

    Args:
        img: BGR图像
        pcb_size_range: {"length_min": 70, "length_max": 80, "width_min": 45, "width_max": 55}
        pixels_per_mm: 像素/毫米比例
        min_area: 最小面积（像素）
        saver: ImageSaver实例，用于保存中间图像
        outline_rgb: RGB范围 dict {r_min, r_max, g_min, g_max, b_min, b_max}

    Returns:
        list[dict]: 每个PCB的信息 {center, bbox, length_px, width_px, contour, angle}
    """
    # --- 1. 颜色分割：RGB范围生成二值图 ---
    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    r, g, b = cv2.split(rgb)

    if outline_rgb is None:
        outline_rgb = {}
    r_min = outline_rgb.get("r_min", 0)
    r_max = outline_rgb.get("r_max", 255)
    g_min = outline_rgb.get("g_min", 56)
    g_max = outline_rgb.get("g_max", 254)
    b_min = outline_rgb.get("b_min", 0)
    b_max = outline_rgb.get("b_max", 255)

    mask = (
        (r >= r_min) & (r <= r_max) &
        (g >= g_min) & (g <= g_max) &
        (b >= b_min) & (b <= b_max)
    ).astype(np.uint8) * 255

    if saver:
        saver.save(mask, "颜色分割二值图")

    # --- 2. 去除面积<100且灰度>127的小色块 ---
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    tmp_contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for cnt in tmp_contours:
        if cv2.contourArea(cnt) >= 100:
            continue
        x, y, w, h = cv2.boundingRect(cnt)
        roi_gray = gray[y:y+h, x:x+w]
        roi_mask = mask[y:y+h, x:x+w]
        if roi_gray[roi_mask > 0].size > 0 and np.mean(roi_gray[roi_mask > 0]) > 127:
            cv2.drawContours(mask, [cnt], -1, 0, -1)

    if saver:
        saver.save(mask, "去小亮色块")

    # --- 3. 找轮廓（过滤后） ---
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # 尺寸过滤范围（像素）
    ppm = pixels_per_mm if pixels_per_mm and pixels_per_mm > 0 else 10.0
    size_range = pcb_size_range or {}
    len_min_px = size_range.get("length_min", 0) * ppm
    len_max_px = size_range.get("length_max", 99999) * ppm
    wid_min_px = size_range.get("width_min", 0) * ppm
    wid_max_px = size_range.get("width_max", 99999) * ppm

    results = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < min_area:
            continue

        # --- 4. 多边形逼近，筛选四边形 ---
        perimeter = cv2.arcLength(cnt, True)
        epsilon = 0.02 * perimeter
        approx = cv2.approxPolyDP(cnt, epsilon, True)

        if len(approx) != 4:
            continue

        # --- 5. 用四边形顶点直接算尺寸 ---
        pts = approx.reshape(4, 2).astype(np.float32)

        # 按左上、右上、右下、左下排序
        s = pts.sum(axis=1)
        d = np.diff(pts, axis=1).flatten()
        ordered = np.zeros((4, 2), dtype=np.float32)
        ordered[0] = pts[np.argmin(s)]   # 左上
        ordered[2] = pts[np.argmax(s)]   # 右下
        ordered[1] = pts[np.argmin(d)]   # 右上
        ordered[3] = pts[np.argmax(d)]   # 左下

        # 用对边平均长度作为长和宽
        top = np.linalg.norm(ordered[1] - ordered[0])
        bottom = np.linalg.norm(ordered[2] - ordered[3])
        left = np.linalg.norm(ordered[3] - ordered[0])
        right = np.linalg.norm(ordered[2] - ordered[1])

        length_px = max((top + bottom) / 2, (left + right) / 2)
        width_px = min((top + bottom) / 2, (left + right) / 2)

        if width_px < 10:
            continue

        # 尺寸过滤
        if not (len_min_px <= length_px <= len_max_px):
            continue
        if not (wid_min_px <= width_px <= wid_max_px):
            continue

        cx = int(ordered[:, 0].mean())
        cy = int(ordered[:, 1].mean())
        bx, by, bw, bh = cv2.boundingRect(cnt)

        # 角度：长边与水平方向的夹角
        if (top + bottom) >= (left + right):
            angle = np.degrees(np.arctan2(ordered[1][1] - ordered[0][1],
                                          ordered[1][0] - ordered[0][0]))
        else:
            angle = np.degrees(np.arctan2(ordered[3][1] - ordered[0][1],
                                          ordered[3][0] - ordered[0][0]))

        # 机械臂旋转角度：短边与竖直方向的夹角，取反使短边竖直
        r_angle = -angle
        # 归一化到 [-90, 90]（矩形旋转180°等价）
        while r_angle > 90:
            r_angle -= 180
        while r_angle < -90:
            r_angle += 180

        results.append({
            "center": (cx, cy),
            "bbox": (bx, by, bw, bh),
            "length_px": round(length_px, 1),
            "width_px": round(width_px, 1),
            "contour": ordered.astype(np.int32).reshape(4, 1, 2),
            "angle": round(angle, 1),
            "r_angle": round(r_angle, 1),
            "rectangularity": 0,
            "circularity": 0,
        })

    # 保存轮廓检测结果
    if saver:
        contour_img = img.copy()
        cv2.drawContours(contour_img, [r["contour"] for r in results], -1, (0, 255, 0), 2)
        saver.save(contour_img, "轮廓检测结果")

    logger.info("检测到 %d 个四边形轮廓", len(results))
    return results


# ======================================================================
# 焊点识别（银白色金属，排除反光）
# ======================================================================
def count_solder_points(img, roi=None, min_area=8, max_area=300):
    """识别图像指定区域内的银白色焊点数量。

    Args:
        img: BGR图像
        roi: (x, y, w, h) 感兴趣区域，None则检测全图

    Returns:
        count: 焊点数量
        points: [(cx, cy), ...] 焊点中心坐标列表（相对于原图）
    """
    if roi is not None:
        x, y, w, h = roi
        region = img[y:y+h, x:x+w]
        offset_x, offset_y = x, y
    else:
        region = img
        offset_x, offset_y = 0, 0

    # --- 排除反光区域 ---
    hsv_raw = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)
    raw_s = hsv_raw[:, :, 1]
    raw_v = hsv_raw[:, :, 2]
    reflection_region = ((raw_s < 80) & (raw_v > 170)).astype(np.uint8) * 255
    kernel_refl = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
    reflection_region = cv2.dilate(reflection_region, kernel_refl, iterations=2)

    # 绿色区域mask
    lower_green = np.array([30, 30, 30])
    upper_green = np.array([90, 255, 255])
    green_mask = cv2.inRange(hsv_raw, lower_green, upper_green)
    kernel_green = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    green_mask_dilated = cv2.dilate(green_mask, kernel_green, iterations=3)

    # 银白色金属检测
    corrected_region = _suppress_reflection(region)
    hsv = cv2.cvtColor(corrected_region, cv2.COLOR_BGR2HSV)
    lower_silver = np.array([0, 0, 210])
    upper_silver = np.array([180, 35, 255])
    mask = cv2.inRange(hsv, lower_silver, upper_silver)

    mask = cv2.bitwise_and(mask, cv2.bitwise_not(reflection_region))
    mask = cv2.bitwise_and(mask, cv2.bitwise_not(green_mask_dilated))

    # 形态学去噪
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=1)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    points = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < min_area or area > max_area:
            continue

        perimeter = cv2.arcLength(cnt, True)
        if perimeter == 0:
            continue
        circularity = 4 * np.pi * area / (perimeter * perimeter)
        if circularity < 0.65:
            continue

        M = cv2.moments(cnt)
        if M["m00"] == 0:
            continue
        cx = int(M["m10"] / M["m00"])
        cy = int(M["m01"] / M["m00"])

        points.append((cx + offset_x, cy + offset_y))

    return len(points), points


# ======================================================================
# 二维码识别
# ======================================================================
def read_qr_code(img, roi=None, downsample=1):
    """识别图像中的二维码内容及位置（zxing-cpp）。

    Args:
        img: BGR图像
        roi: (x, y, w, h) 感兴趣区域，None则检测整张图
        downsample: 降采样倍数，默认1（不降采样）

    Returns:
        tuple: (text: str, corners: list | None)
            - text: 二维码内容，未识别到返回空字符串
            - corners: [(x,y), (x,y), (x,y), (x,y)] 四角坐标（左上→右上→右下→左下），无结果返回None
    """
    if roi is not None:
        x, y, w, h = roi
        region = img[y:y+h, x:x+w]
    else:
        region = img

    if region.size == 0:
        return "", None

    try:
        if downsample > 1:
            region = cv2.resize(region, (region.shape[1] // downsample, region.shape[0] // downsample))
        result = zxingcpp.read_barcode(region)
        if result is not None:
            logger.info("二维码识别结果: %s", result.text)
            pos = result.position
            corners = [
                (pos.top_left.x, pos.top_left.y),
                (pos.top_right.x, pos.top_right.y),
                (pos.bottom_right.x, pos.bottom_right.y),
                (pos.bottom_left.x, pos.bottom_left.y),
            ]
            return result.text, corners
    except Exception as e:
        logger.warning("二维码识别异常: %s", e)

    return "", None


# ======================================================================
# 绘制检测结果
# ======================================================================
def draw_results(img, results):
    """在图像上绘制检测结果：检测框、尺寸、焊盘数量、二维码信息。

    Args:
        img: 原始BGR图像（会复制一份，不修改原图）
        results: process_frame() 返回的PCB信息列表

    Returns:
        annotated: 标注后的BGR图像
    """
    annotated = img.copy()

    for item in results:
        cx, cy = item["img_pos"]
        length_px = item["length_px"]
        width_px = item["width_px"]
        has_pcb = length_px > 0 and width_px > 0

        # 有PCB板时画多边形轮廓和中心标记
        if has_pcb:
            contour = item.get("contour")
            if contour is not None:
                cv2.polylines(annotated, [contour], isClosed=True,
                              color=(0, 255, 0), thickness=2)
            cv2.drawMarker(annotated, (cx, cy), (0, 0, 255),
                            cv2.MARKER_CROSS, 20, 2)
            cv2.circle(annotated, (cx, cy), 4, (0, 0, 255), -1)

        # 焊点绘制（独立于PCB检测）
        for sx, sy in item.get("solder_points", []):
            cv2.circle(annotated, (sx, sy), 5, (255, 0, 0), -1)

        # 二维码区域绘制
        qr_corners = item.get("qr_corners")
        if qr_corners:
            pts = np.array(qr_corners, dtype=np.int32).reshape((-1, 1, 2))
            cv2.polylines(annotated, [pts], isClosed=True,
                          color=(0, 255, 255), thickness=2)
            qr_center = item.get("qr_center")
            if qr_center:
                cv2.drawMarker(annotated, qr_center, (0, 255, 255),
                               cv2.MARKER_CROSS, 12, 1)

        # 标签位置：有PCB板用轮廓外接矩形左上角，无PCB板用图像左上角
        if has_pcb:
            bbox = cv2.boundingRect(contour if contour is not None else np.array([[cx, cy]]))
            label_x, label_y = bbox[0], bbox[1] - 6
            label1 = f"PCB {item['length_mm']}x{item['width_mm']}mm"
        else:
            label_x, label_y = 10, 30
            label1 = "No PCB"

        label2 = f"Solder: {item.get('solder_count', 0)}"
        qr = item.get("qr_code", "")
        label3 = f"QR: {qr[:20]}" if qr else "QR: N/A"

        cv2.putText(annotated, label1, (label_x, label_y - 32),
                     cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
        cv2.putText(annotated, label2, (label_x, label_y - 16),
                     cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)
        cv2.putText(annotated, label3, (label_x, label_y),
                     cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 200, 255), 1)

    return annotated


def pixel_to_mm(px, pixels_per_mm):
    """像素转毫米。"""
    return round(px / pixels_per_mm, 1) if pixels_per_mm > 0 else 0


# ======================================================================
# 综合视觉处理：检测PCB → 识别焊点 → 标定转换
# ======================================================================
def process_frame(img, calibrator=None, config=None):
    """处理单帧图像，返回PCB板信息列表。

    Args:
        img: BGR图像
        calibrator: Calibrator对象（坐标转换用）
        config: dict，PCB配置参数 {
            "pixels_per_mm": 10.0,
            "length_min_mm": 70, "length_max_mm": 80,
            "width_min_mm": 45, "width_max_mm": 55,
        }

    Returns:
        list[dict]: 每个PCB的信息 {
            "img_pos": (cx, cy),
            "phys_pos": (x, y) | None,
            "length_px", "width_px", "length_mm", "width_mm",
            "solder_count", "solder_points",
            "status": "OK" | "NG",
            "display": str,
        }
    """
    cfg = config or {}
    pixels_per_mm = cfg.get("pixels_per_mm", 10.0)

    # 创建图像保存器
    saver = ImageSaver("pcb")
    saver.save(img, "原始图像")

    # 构建尺寸范围
    pcb_size_range = {
        "length_min": cfg.get("length_min_mm", 0),
        "length_max": cfg.get("length_max_mm", 99999),
        "width_min": cfg.get("width_min_mm", 0),
        "width_max": cfg.get("width_max_mm", 99999),
    }

    pcb_list = detect_pcb(img, pcb_size_range=pcb_size_range,
                           pixels_per_mm=pixels_per_mm, saver=saver,
                           outline_rgb=cfg.get("outline_rgb"))

    # 二维码：直接对整张图识别，不依赖是否检测到PCB板
    qr_code, qr_corners = read_qr_code(img)

    # 二维码中心及物理坐标
    qr_center = None
    qr_phys_pos = None
    if qr_corners:
        qr_cx = int(sum(p[0] for p in qr_corners) / 4)
        qr_cy = int(sum(p[1] for p in qr_corners) / 4)
        qr_center = (qr_cx, qr_cy)
        if calibrator is not None and calibrator.is_calibrated:
            qr_phys_pos = calibrator.img_to_phys(qr_center)

    # 焊盘：对整张图识别，不依赖是否检测到PCB板
    solder_count, solder_pts = count_solder_points(img)

    results = []

    for pcb in pcb_list:
        cx, cy = pcb["center"]
        length_mm = pixel_to_mm(pcb["length_px"], pixels_per_mm)
        width_mm = pixel_to_mm(pcb["width_px"], pixels_per_mm)

        phys_pos = None
        if calibrator is not None and calibrator.is_calibrated:
            phys_pos = calibrator.img_to_phys((cx, cy))

        status = "OK"

        display_parts = [f"(接收) PCB {length_mm}x{width_mm}mm"]
        display_parts.append(f"焊盘:{solder_count}")
        display_parts.append(f"二维码:{qr_code or 'N/A'}")
        display_parts.append(f"旋转:{pcb['r_angle']}°")

        results.append({
            "img_pos": (cx, cy),
            "phys_pos": phys_pos,
            "length_px": pcb["length_px"],
            "width_px": pcb["width_px"],
            "length_mm": length_mm,
            "width_mm": width_mm,
            "contour": pcb["contour"],
            "angle": pcb["angle"],
            "r_angle": pcb["r_angle"],
            "rectangularity": pcb.get("rectangularity", 0),
            "circularity": pcb.get("circularity", 0),
            "solder_count": solder_count,
            "solder_points": solder_pts,
            "qr_code": qr_code,
            "qr_corners": qr_corners,
            "qr_center": qr_center,
            "qr_phys_pos": qr_phys_pos,
            "status": status,
            "display": ", ".join(display_parts),
        })

    # 保存最终标注图
    annotated = draw_results(img, results)
    if saver:
        saver.save(annotated, "最终标注结果")

    logger.info("识别到 %d 块PCB板", len(results))
    return results, saver
