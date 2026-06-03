# -- coding: utf-8 --
"""人脸识别模块 —— 使用电脑前置摄像头进行人脸检测与识别。

功能:
  1. detect_face(): 打开前置摄像头检测人脸（无需训练）
  2. init_face_recognition(): 从 face_data/ 目录加载训练数据，初始化 LBPH 识别器
  3. detect_and_recognize(): 检测 + 识别特定人员，返回匹配度

face_data 目录结构:
  face_data/
    张三/          ← 文件夹名即人名
      1.jpg
      2.jpg
    李四/
      1.jpg

如果 face_data 为空或不存在，退化为纯检测模式。
"""
import sys
import os
import cv2
import time
import logging
import numpy as np

logger = logging.getLogger(__name__)

# Haar 级联分类器（检测用）
_cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
_face_cascade = cv2.CascadeClassifier(_cascade_path)

# 识别器与人名列表（模块级缓存）
_recognizer = None
_names = []
_recognizer_ready = False


def init_face_recognition(data_dir="face_data"):
    """从目录加载人脸图片，训练 LBPH 识别器。

    Args:
        data_dir: 人脸数据目录路径（相对于项目根目录）

    Returns:
        bool: 是否成功加载训练数据
    """
    global _recognizer, _names, _recognizer_ready

    if not os.path.isdir(data_dir):
        logger.warning("人脸数据目录不存在: %s", data_dir)
        _recognizer_ready = False
        return False

    faces = []
    labels = []
    _names = []
    label_id = 0

    for person_name in sorted(os.listdir(data_dir)):
        person_dir = os.path.join(data_dir, person_name)
        if not os.path.isdir(person_dir):
            continue

        _names.append(person_name)
        logger.info("加载人脸数据: %s (label=%d)", person_name, label_id)

        for fname in os.listdir(person_dir):
            fpath = os.path.join(person_dir, fname)
            img = cv2.imread(fpath, cv2.IMREAD_GRAYSCALE)
            if img is None:
                continue

            # 检测人脸区域（确保训练图片也经过裁剪）
            detected = _face_cascade.detectMultiScale(img, 1.1, 4)
            if len(detected) > 0:
                x, y, w, h = detected[0]
                face_roi = img[y:y+h, x:x+w]
            else:
                # 整张图当人脸用（可能本身就是裁剪好的）
                face_roi = img

            face_roi = cv2.resize(face_roi, (200, 200))
            faces.append(face_roi)
            labels.append(label_id)

        label_id += 1

    if not faces:
        logger.warning("未找到任何人脸训练图片")
        _recognizer_ready = False
        return False

    _recognizer = cv2.face.LBPHFaceRecognizer_create()
    _recognizer.train(faces, np.array(labels))
    _recognizer_ready = True
    logger.info("人脸训练完成: %d 张图片, %d 人", len(faces), len(_names))
    return True


def recognize_face(gray_frame):
    """在灰度图中检测人脸并识别身份。

    Args:
        gray_frame: 灰度图像

    Returns:
        dict: {
            "detected": bool,       # 是否检测到人脸
            "matched": bool,        # 是否匹配成功
            "name": str,            # 匹配到的人名
            "confidence": float,    # 置信度 (0~100, 越高越匹配)
        }
    """
    result = {"detected": False, "matched": False, "name": "", "confidence": 0.0}

    faces = _face_cascade.detectMultiScale(gray_frame, 1.3, 5)
    if len(faces) == 0:
        return result

    result["detected"] = True

    # 取最大的人脸
    areas = [w * h for (_, _, w, h) in faces]
    idx = np.argmax(areas)
    x, y, w, h = faces[idx]

    face_roi = gray_frame[y:y+h, x:x+w]
    face_roi = cv2.resize(face_roi, (200, 200))

    if _recognizer is None or not _recognizer_ready:
        # 无识别器，仅检测
        result["matched"] = True
        result["name"] = "未知"
        result["confidence"] = 100.0
        return result

    label, distance = _recognizer.predict(face_roi)
    # LBPH distance 越小越相似，转换为 0~100 匹配度
    # distance < 50 → 高匹配, distance > 100 → 低匹配
    confidence = max(0.0, min(100.0, 100.0 - distance))

    if label < len(_names):
        result["name"] = _names[label]
    else:
        result["name"] = "未知"

    result["confidence"] = round(confidence, 1)
    result["matched"] = True

    logger.info("人脸识别: name=%s, distance=%.1f, confidence=%.1f",
                result["name"], distance, confidence)

    return result, (x, y, w, h)


def detect_face(camera_index=0, callback=None, timeout_sec=15,
                recognizer_enabled=False, match_threshold=60):
    """打开电脑前置摄像头检测人脸，可选进行人脸识别。

    Args:
        camera_index: 摄像头索引（0=前置摄像头）
        callback: callback(message: str) 状态回调
        timeout_sec: 超时秒数
        recognizer_enabled: 是否启用人脸识别
        match_threshold: 匹配度阈值，低于此值视为不匹配

    Returns:
        dict: {
            "detected": bool,
            "matched": bool,
            "name": str,
            "confidence": float,
        }
    """
    def _notify(msg):
        if callback:
            callback(msg)

    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        _notify("无法打开摄像头")
        return {"detected": False, "matched": False, "name": "", "confidence": 0.0}

    _notify("正在打开摄像头，请正对屏幕...")

    start = time.time()
    best_result = {"detected": False, "matched": False, "name": "", "confidence": 0.0}
    best_face_rect = None

    while time.time() - start < timeout_sec:
        ret, frame = cap.read()
        if not ret:
            break

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        if recognizer_enabled and _recognizer_ready:
            recog_result, face_rect = recognize_face(gray)
        else:
            # 纯检测模式
            faces = _face_cascade.detectMultiScale(gray, 1.3, 5)
            if len(faces) > 0:
                areas = [w * h for (_, _, w, h) in faces]
                idx = np.argmax(areas)
                face_rect = tuple(faces[idx])
                recog_result = {
                    "detected": True, "matched": True,
                    "name": "未知", "confidence": 100.0,
                }
            else:
                recog_result = {
                    "detected": False, "matched": False,
                    "name": "", "confidence": 0.0,
                }
                face_rect = None

        # 绘制结果
        if face_rect is not None:
            x, y, w, h = face_rect
            conf = recog_result["confidence"]

            if recognizer_enabled and _recognizer_ready:
                # 识别模式：根据阈值显示颜色
                if conf >= match_threshold:
                    color = (0, 255, 0)
                    label_text = f"{recog_result['name']} {conf:.0f}%"
                else:
                    color = (0, 165, 255)
                    label_text = f"Unknown {conf:.0f}%"
            else:
                color = (0, 255, 0)
                label_text = "Face Detected"

            cv2.rectangle(frame, (x, y), (x + w, y + h), color, 3)
            cv2.putText(frame, label_text, (x, y - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)

        cv2.imshow("Face Detection", frame)

        if recog_result["detected"]:
            if not recognizer_enabled or not _recognizer_ready:
                # 纯检测模式，检测到即成功
                best_result = recog_result
                _notify("检测到人脸")
                cv2.waitKey(1000)
                break
            elif recog_result["confidence"] >= match_threshold:
                # 识别模式，匹配度达标
                best_result = recog_result
                _notify(f"识别成功: {recog_result['name']}, 匹配度: {recog_result['confidence']:.1f}%")
                cv2.waitKey(1500)
                break
            else:
                # 检测到但匹配度不够，记录最佳结果
                if recog_result["confidence"] > best_result["confidence"]:
                    best_result = recog_result

        if cv2.waitKey(1) & 0xFF == ord('q'):
            _notify("用户取消识别")
            break

    cap.release()
    cv2.destroyAllWindows()

    if not best_result["detected"]:
        _notify("人脸识别超时，未检测到人脸")
    elif recognizer_enabled and _recognizer_ready and best_result["confidence"] < match_threshold:
        _notify(f"匹配度不足: {best_result['confidence']:.1f}% < {match_threshold}%")

    return best_result
