# -*- coding: utf-8 -*-
"""圆环展开脚本 —— 检测圆形瓶盖，提取圆环区域并按0°-360°展开为矩形图像。

流程:
    1. 检测 270-330px 直径的圆形
    2. 按 0.6 比例取圆环（内径=r*0.6, 外径=r）
    3. 找最长连续白色区段，以其中心作为起始角度展开
    4. 保存展开结果
"""
import logging
import math
import os

import cv2
import numpy as np

logger = logging.getLogger(__name__)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s'))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


def detect_circles(img, diameter_min=270, diameter_max=330):
    """检测指定直径范围的圆形。

    Args:
        img: BGR图像
        diameter_min: 最小直径(px)
        diameter_max: 最大直径(px)

    Returns:
        list[tuple]: [(cx, cy, r), ...] 圆心和半径
    """
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (9, 9), 2)

    r_min = diameter_min // 2
    r_max = diameter_max // 2
    min_dist = int(r_min * 1.5 * 2)

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
    return [(int(c[0]), int(c[1]), int(c[2])) for c in circles[0]]


def find_longest_white_block(img, cx, cy, r, ratio=0.6, samples=360):
    """采样各角度的圆环亮度，找到最长连续白色区段的中心作为起始角度。

    在圆环中间半径处采样一圈像素，按阈值二值化后找最长连续高亮段，
    返回其中心角度。这样文字（暗色）会被完整聚集，不会分散在左右两端。

    Args:
        img: BGR图像
        cx, cy: 圆心坐标
        r: 圆半径
        ratio: 圆环内径比例
        samples: 采样角度数

    Returns:
        float: 最佳起始角度（弧度）
    """
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    r_inner = int(r * ratio)
    r_mid = (r + r_inner) // 2

    # 采样亮度
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

    # 用均值作为阈值二值化
    threshold = np.mean(brightness)
    is_white = [b > threshold for b in brightness]

    # 找最长连续白色区段（处理环形回绕）
    best_start, best_len = 0, 0
    cur_start, cur_len = -1, 0

    # 遍历两倍长度以处理首尾相连的情况
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

    # 限制长度不超过 samples（防止全白时重复计数）
    best_len = min(best_len, samples)

    # 计算白色区段的中心角度
    center_idx = (best_start + best_len // 2) % samples
    best_angle = 2.0 * math.pi * center_idx / samples

    logger.info("连续白色检测: 阈值=%.0f, 最长白色段=%d° (起始=%d°, 中心=%d°)",
                threshold, best_len, best_start, center_idx)
    logger.info("圆环亮度采样: 均值=%.0f, 最亮=%.0f @ %d°, 最暗=%.0f @ %d°",
                threshold, max(brightness), int(np.argmax(brightness)),
                min(brightness), int(np.argmin(brightness)))

    return best_angle


def unwrap_ring(img, cx, cy, r, ratio=0.6, output_width=1080, start_angle=None):
    """将圆环区域按极坐标展开为矩形。

    Args:
        img: BGR图像
        cx, cy: 圆心坐标
        r: 圆半径(px)
        ratio: 圆环内径比例（内径 = r * ratio）
        output_width: 展开后矩形的宽度（对应360°）
        start_angle: 起始角度（弧度），None则自动寻找最亮区域

    Returns:
        np.ndarray: 展开后的矩形BGR图像
    """
    r_inner = int(r * ratio)
    r_outer = r
    ring_width = r_outer - r_inner  # 圆环径向宽度

    # 自动寻找最佳起始角度
    if start_angle is None:
        start_angle = find_longest_white_block(img, cx, cy, r, ratio)
        logger.info("自动选择起始角度: %.1f°", math.degrees(start_angle))

    # 角度步长：每列对应1°
    n_cols = output_width
    n_rows = ring_width

    # 构建极坐标映射表
    map_x = np.zeros((n_rows, n_cols), dtype=np.float32)
    map_y = np.zeros((n_rows, n_cols), dtype=np.float32)

    for col in range(n_cols):
        # 角度：从start_angle开始，绕一圈
        angle = start_angle + 2.0 * math.pi * col / n_cols
        cos_a = math.cos(angle)
        sin_a = math.sin(angle)

        for row in range(n_rows):
            # 当前半径：从外向内（顶部=外径，底部=内径）
            radius = r_outer - row
            map_x[row, col] = cx + radius * cos_a
            map_y[row, col] = cy + radius * sin_a

    # 重映射
    unwrapped = cv2.remap(img, map_x, map_y, cv2.INTER_LINEAR,
                          borderMode=cv2.BORDER_WRAP)
    return unwrapped


def process_image(img, ratio=0.6, output_width=1080):
    """处理单张图片：检测圆形并展开圆环。

    Args:
        img: BGR图像
        ratio: 圆环内径比例
        output_width: 展开矩形宽度

    Returns:
        list[np.ndarray]: 所有检测到的圆环展开结果
        list[tuple]: 对应的圆心和半径 [(cx, cy, r), ...]
    """
    circles = detect_circles(img)
    if not circles:
        print("未检测到圆形")
        return [], []

    print(f"检测到 {len(circles)} 个圆形:")
    results = []
    for i, (cx, cy, r) in enumerate(circles):
        diameter = r * 2
        r_inner = int(r * ratio)
        print(f"  #{i+1}: 圆心=({cx}, {cy}), 半径={r}px, 直径={diameter}px, "
              f"环宽={r - r_inner}px (内径={r_inner}px)")

        unwrapped = unwrap_ring(img, cx, cy, r, ratio, output_width)
        results.append(unwrapped)

    return results, circles


def draw_detections(img, circles, ratio=0.6):
    """在原图上绘制检测到的圆和圆环。

    Args:
        img: 原始BGR图像
        circles: [(cx, cy, r), ...]
        ratio: 圆环内径比例

    Returns:
        np.ndarray: 标注后的图像
    """
    annotated = img.copy()
    for cx, cy, r in circles:
        # 外圆（绿色）
        cv2.circle(annotated, (cx, cy), r, (0, 255, 0), 2)
        # 内圆（黄色）
        r_inner = int(r * ratio)
        cv2.circle(annotated, (cx, cy), r_inner, (0, 255, 255), 2)
        # 圆心标记
        cv2.drawMarker(annotated, (cx, cy), (0, 0, 255),
                       cv2.MARKER_CROSS, 10, 2)
        # 标注直径
        cv2.putText(annotated, f"d={r*2}px", (cx - 30, cy - r - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
    return annotated


def main():
    # 硬编码路径
    script_dir = os.path.dirname(os.path.abspath(__file__))
    image_path = os.path.join(script_dir, "picture", "20260601_142445_cap", "01_original.png")
    out_dir = os.path.join(script_dir, "picture", "20260601_142445_cap", "01_original_ring")

    ratio = 0.6
    output_width = 1080

    # 读取图片
    img = cv2.imread(image_path)
    if img is None:
        print(f"错误：无法读取图片 {image_path}")
        return

    print(f"图片尺寸: {img.shape[1]}x{img.shape[0]}")

    # 处理
    results, circles = process_image(img, ratio, output_width)

    if not results:
        return

    # 绘制检测标注图
    annotated = draw_detections(img, circles, ratio)

    # 确保输出目录存在
    os.makedirs(out_dir, exist_ok=True)

    # 保存检测标注图
    det_path = os.path.join(out_dir, "detection.png")
    cv2.imwrite(det_path, annotated)
    print(f"保存检测标注: {det_path}")

    # 保存每个圆环展开结果
    for i, unwrapped in enumerate(results):
        out_path = os.path.join(out_dir, f"ring_{i+1}.png")
        cv2.imwrite(out_path, unwrapped)
        h, w = unwrapped.shape[:2]
        print(f"保存展开结果 #{i+1}: {out_path} ({w}x{h})")

    print("完成！")


if __name__ == "__main__":
    main()
