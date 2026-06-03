# -- coding: utf-8 --
"""相机管理模块 —— 封装MVS工业相机的打开、取帧、关闭。

依赖 camera.mvs 提供的 MvCamera SDK。
"""
import sys
import os
import logging
import numpy as np
import cv2
from ctypes import *

# 确保项目根目录在 sys.path 中
_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _root not in sys.path:
    sys.path.insert(0, _root)

from camera.mvs import (
    MvCamera, MV_CC_DEVICE_INFO_LIST, MV_FRAME_OUT_INFO_EX,
    MV_CC_PIXEL_CONVERT_PARAM, MV_GIGE_DEVICE, MV_USB_DEVICE,
    MV_OK, MV_TRIGGER_MODE_OFF, MV_ACCESS_Exclusive,
    PixelType_Gvsp_BGR8_Packed, memset, sizeof, byref, unload_dll,
)

logger = logging.getLogger(__name__)


class CameraManager:
    """MVS工业相机管理器，提供 open / grab / close 接口。"""

    def __init__(self):
        self._cam = None
        self._opened = False

    # ------------------------------------------------------------------
    # 打开相机
    # ------------------------------------------------------------------
    def open(self, device_index: int = 0, exposure_time: float = 40000.0) -> bool:
        """打开指定索引的相机设备，成功返回 True。"""
        if self._opened:
            return True

        try:
            cam = MvCamera()

            device_list = MV_CC_DEVICE_INFO_LIST()
            memset(byref(device_list), 0, sizeof(device_list))

            ret = MvCamera.MV_CC_EnumDevices(
                MV_GIGE_DEVICE | MV_USB_DEVICE, device_list
            )
            if ret != MV_OK:
                logger.error("枚举设备失败: 0x%08x", ret)
                return False
            if device_list.nDeviceNum == 0:
                logger.error("未发现相机设备")
                return False
            if device_index >= device_list.nDeviceNum:
                logger.error("设备索引 %d 超出范围", device_index)
                return False

            st_dev_info = device_list.pDeviceInfo[device_index].contents
            ret = cam.MV_CC_CreateHandle(st_dev_info)
            if ret != MV_OK:
                logger.error("创建句柄失败: 0x%08x", ret)
                return False

            ret = cam.MV_CC_OpenDevice(MV_ACCESS_Exclusive, 0)
            if ret != MV_OK:
                logger.error("打开设备失败: 0x%08x", ret)
                cam.MV_CC_DestroyHandle()
                return False

            # 设置连续采集模式
            cam.MV_CC_SetEnumValue("TriggerMode", MV_TRIGGER_MODE_OFF)
            # 设置曝光时间（从配置读取）
            cam.MV_CC_SetFloatValue("ExposureTime", exposure_time)
            # 设置增益
            cam.MV_CC_SetFloatValue("Gain", 15.0)

            ret = cam.MV_CC_StartGrabbing()
            if ret != MV_OK:
                logger.error("开始取流失败: 0x%08x", ret)
                cam.MV_CC_CloseDevice()
                cam.MV_CC_DestroyHandle()
                return False

            self._cam = cam
            self._opened = True
            logger.info("相机已打开")
            return True

        except Exception as e:
            logger.error("打开相机异常: %s", e)
            return False

    # ------------------------------------------------------------------
    # 取一帧
    # ------------------------------------------------------------------
    def grab_frame(self, timeout_ms: int = 3000):
        """取一帧图像，返回 BGR numpy 数组；失败返回 None。"""
        if not self._opened or self._cam is None:
            return None

        st_frame_info = MV_FRAME_OUT_INFO_EX()
        memset(byref(st_frame_info), 0, sizeof(st_frame_info))
        buf = (c_ubyte * (4096 * 4096 * 3))()

        ret = self._cam.MV_CC_GetOneFrameTimeout(buf, len(buf), st_frame_info, timeout_ms)
        if ret != MV_OK:
            return None

        w, h = st_frame_info.nWidth, st_frame_info.nHeight
        pixel_type = st_frame_info.enPixelType
        frame_len = st_frame_info.nFrameLen

        # 像素格式转换 → BGR8
        n_dst_size = w * h * 3
        convert_param = MV_CC_PIXEL_CONVERT_PARAM()
        memset(byref(convert_param), 0, sizeof(convert_param))
        convert_param.nWidth = w
        convert_param.nHeight = h
        convert_param.enSrcPixelType = pixel_type
        convert_param.pSrcData = buf
        convert_param.nSrcDataLen = frame_len
        convert_param.enDstPixelType = PixelType_Gvsp_BGR8_Packed
        convert_param.nDstBufferSize = n_dst_size
        dst_buf = (c_ubyte * n_dst_size)()
        convert_param.pDstBuffer = dst_buf

        ret = self._cam.MV_CC_ConvertPixelType(convert_param)
        if ret == MV_OK:
            img = np.frombuffer(dst_buf, dtype=np.uint8).reshape(h, w, 3).copy()
        else:
            # 回退：灰度或已BGR
            if frame_len == w * h:
                gray = np.frombuffer(buf, dtype=np.uint8, count=w * h).reshape(h, w)
                img = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
            else:
                img = np.frombuffer(buf, dtype=np.uint8, count=w * h * 3).reshape(h, w, 3)

        return img

    # ------------------------------------------------------------------
    # 关闭相机
    # ------------------------------------------------------------------
    def close(self):
        """停止取流、关闭设备、释放资源。"""
        if self._cam is not None:
            try:
                self._cam.MV_CC_StopGrabbing()
            except Exception:
                pass
            try:
                self._cam.MV_CC_CloseDevice()
            except Exception:
                pass
            try:
                self._cam.MV_CC_DestroyHandle()
            except Exception:
                pass
            self._cam = None
            self._opened = False
            try:
                unload_dll()
            except Exception:
                pass
            logger.info("相机已关闭")

    def set_exposure(self, exposure_time: float) -> bool:
        """动态设置曝光时间（相机必须已打开）。成功返回 True。"""
        if not self._opened or self._cam is None:
            logger.warning("相机未打开，无法设置曝光时间")
            return False
        try:
            self._cam.MV_CC_SetFloatValue("ExposureTime", exposure_time)
            logger.info("曝光时间已设置为 %.1f μs", exposure_time)
            return True
        except Exception as e:
            logger.error("设置曝光时间失败: %s", e)
            return False

    @property
    def is_open(self) -> bool:
        return self._opened

    def __del__(self):
        self.close()
