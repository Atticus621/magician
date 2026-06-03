# -- coding: utf-8 --
"""人脸识别模块 —— 使用电脑前置摄像头检测人脸。

只需检测到人脸即算成功，无需训练。
基于 OpenCV Haar 级联分类器。
"""
import sys
import os
import cv2
import time

# Haar级联分类器
_cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
_face_cascade = cv2.CascadeClassifier(_cascade_path)


def detect_face(camera_index=0, callback=None, timeout_sec=15):
    """打开电脑前置摄像头检测人脸，检测到即返回 True。

    Args:
        camera_index: 摄像头索引（0=前置摄像头）
        callback: callback(message: str) 状态回调
        timeout_sec: 超时秒数

    Returns:
        True 检测到人脸 / False 超时或失败
    """
    def _notify(msg):
        if callback:
            callback(msg)

    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        _notify("无法打开摄像头")
        return False

    _notify("正在打开摄像头，请正对屏幕...")

    start = time.time()
    detected = False

    while time.time() - start < timeout_sec:
        ret, frame = cap.read()
        if not ret:
            break

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = _face_cascade.detectMultiScale(gray, 1.3, 5)

        for (x, y, w, h) in faces:
            # 检测到人脸
            cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 3)
            cv2.putText(frame, "Face Detected!", (x, y - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
            detected = True

        cv2.imshow("Face Detection", frame)

        if detected:
            _notify("人脸识别成功")
            # 显示一会结果
            cv2.waitKey(1000)
            break

        if cv2.waitKey(1) & 0xFF == ord('q'):
            _notify("用户取消识别")
            break

    cap.release()
    cv2.destroyAllWindows()

    if not detected:
        _notify("人脸识别超时，未检测到人脸")

    return detected
