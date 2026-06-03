# MVS Camera API Reference

海康威视 MVS (Machine Vision System) Python SDK 使用参考。

## 环境配置

```python
from camera.mvs import *
```

DLL加载路径、MvImport模块路径、所有API符号均已封装在 `camera/mvs.py` 中。

退出时释放DLL：
```python
from camera.mvs import unload_dll
# ... 程序结束时调用
unload_dll()
```

## 基本流程

```
枚举设备 -> 创建句柄 -> 打开设备 -> 设置参数 -> 开始取流 -> 获取图像 -> 停止取流 -> 关闭设备 -> 销毁句柄
```

## API 速查

### 设备枚举与连接

```python
# 枚举设备 (GigE + USB)
device_list = MV_CC_DEVICE_INFO_LIST()
memset(byref(device_list), 0, sizeof(device_list))
ret = MvCamera.MV_CC_EnumDevices(MV_GIGE_DEVICE | MV_USB_DEVICE, device_list)
# 返回 MV_OK(0) 表示成功，device_list.nDeviceNum 为设备数量

# 创建相机实例
cam = MvCamera()

# 选择设备并创建句柄
st_dev_info = device_list.pDeviceInfo[0].contents
ret = cam.MV_CC_CreateHandle(st_dev_info)

# 打开设备
ret = cam.MV_CC_OpenDevice(MV_ACCESS_Exclusive, 0)

# GigE相机：设置最佳包大小
if st_dev_info.nTLayerType == MV_GIGE_DEVICE:
    nPacketSize = cam.MV_CC_GetOptimalPacketSize()
    if nPacketSize > 0:
        cam.MV_CC_SetIntValue("GevSCPSPacketSize", nPacketSize)
```

### 参数设置

```python
# 曝光时间 (单位: 微秒 us)
cam.MV_CC_SetFloatValue("ExposureTime", 3500.0)  # 3.5ms

# 增益
cam.MV_CC_SetFloatValue("Gain", 10.0)

# 触发模式: 0=Off(连续采集), 1=On(触发模式)
cam.MV_CC_SetEnumValue("TriggerMode", MV_TRIGGER_MODE_OFF)

# 触发源: 0=Line0, 7=Software
cam.MV_CC_SetEnumValue("TriggerSource", MV_TRIGGER_SOURCE_SOFTWARE)

# 白平衡: 0=Off, 1=Continuous, 2=Once
cam.MV_CC_SetEnumValue("BalanceWhiteAuto", MV_BALANCEWHITE_AUTO_OFF)

# 帧率控制
cam.MV_CC_SetFloatValue("AcquisitionFrameRate", 30.0)
```

### 参数获取

```python
# 获取整型值
stIntValue = MVCC_INTVALUE()
memset(byref(stIntValue), 0, sizeof(MVCC_INTVALUE))
cam.MV_CC_GetIntValue("PayloadSize", stIntValue)
nPayloadSize = stIntValue.nCurValue
# stIntValue.nMin, stIntValue.nMax, stIntValue.nInc

# 获取浮点值
stFloatValue = MVCC_FLOATVALUE()
memset(byref(stFloatValue), 0, sizeof(MVCC_FLOATVALUE))
cam.MV_CC_GetFloatValue("ExposureTime", stFloatValue)
# stFloatValue.fCurValue, stFloatValue.fMin, stFloatValue.fMax

# 获取枚举值
stEnumValue = MVCC_ENUMVALUE()
memset(byref(stEnumValue), 0, sizeof(MVCC_ENUMVALUE))
cam.MV_CC_GetEnumValue("TriggerMode", stEnumValue)
# stEnumValue.nCurValue

# 获取布尔值
bValue = c_bool()
cam.MV_CC_GetBoolValue("ReverseX", bValue)

# 获取字符串值
stStrValue = MVCC_STRINGVALUE()
cam.MV_CC_GetStringValue("DeviceModelName", stStrValue)
```

### 取流

```python
# 开始取流
ret = cam.MV_CC_StartGrabbing()

# 主动取帧
stFrameInfo = MV_FRAME_OUT_INFO_EX()
memset(byref(stFrameInfo), 0, sizeof(stFrameInfo))
data_buf = (c_ubyte * nPayloadSize)()

ret = cam.MV_CC_GetOneFrameTimeout(data_buf, nPayloadSize, stFrameInfo, 1000)
# ret == MV_OK 表示成功
# stFrameInfo.nWidth, nHeight, enPixelType, nFrameNum, nFrameLen

# 停止取流
cam.MV_CC_StopGrabbing()
```

### 回调取流

```python
# 定义回调函数
def image_callback(pData, pFrameInfo, pUser):
    frame_info = pFrameInfo.contents
    print(f"Frame: {frame_info.nWidth}x{frame_info.nHeight}, Num={frame_info.nFrameNum}")
    # 处理 pData 中的图像数据...

# 注册回调 (在 StartGrabbing 之前调用)
CALLBACK_FUNC = CFUNCTYPE(None, POINTER(c_ubyte), POINTER(MV_FRAME_OUT_INFO_EX), c_void_p)
cb_func = CALLBACK_FUNC(image_callback)
cam.MV_CC_RegisterImageCallBackEx(cb_func, None)

cam.MV_CC_StartGrabbing()
```

### 像素格式转换

```python
# 转换为 BGR8 (OpenCV格式)
nDstSize = nWidth * nHeight * 3
convert_param = MV_CC_PIXEL_CONVERT_PARAM()
memset(byref(convert_param), 0, sizeof(convert_param))
convert_param.nWidth = nWidth
convert_param.nHeight = nHeight
convert_param.enSrcPixelType = nPixelType        # 源格式
convert_param.pSrcData = data_buf                 # 源数据
convert_param.nSrcDataLen = nFrameLen             # 源数据长度
convert_param.enDstPixelType = PixelType_Gvsp_BGR8_Packed  # 目标格式
convert_param.nDstBufferSize = nDstSize
dst_buf = (c_ubyte * nDstSize)()
convert_param.pDstBuffer = dst_buf

ret = cam.MV_CC_ConvertPixelType(convert_param)

# 转为numpy数组供OpenCV使用
import numpy as np
img = np.frombuffer(dst_buf, dtype=np.uint8).reshape(nHeight, nWidth, 3)
```

### 保存图片

```python
# 通过SDK保存
save_param = MV_SAVE_IMAGE_PARAM_EX()
save_param.pData = data_buf
save_param.nDataLen = nFrameLen
save_param.nWidth = nWidth
save_param.nHeight = nHeight
save_param.enPixelType = nPixelType
save_param.enImageType = MV_Image_Jpeg  # MV_Image_Bmp, MV_Image_Png, MV_Image_Jpeg
save_param.nJpgQuality = 95
img_buf = (c_ubyte * (nWidth * nHeight * 3))()
save_param.pImageBuffer = img_buf
save_param.nBufferSize = nWidth * nHeight * 3
cam.MV_CC_SaveImageEx2(save_param)

# 或直接用OpenCV保存 (推荐)
import cv2
cv2.imwrite("frame.jpg", img)
```

### 清理资源

```python
cam.MV_CC_StopGrabbing()
cam.MV_CC_CloseDevice()
cam.MV_CC_DestroyHandle()
```

## 常用像素格式常量

| 常量 | 说明 |
|------|------|
| `PixelType_Gvsp_Mono8` | 8位灰度 |
| `PixelType_Gvsp_BGR8_Packed` | BGR8 (OpenCV默认) |
| `PixelType_Gvsp_RGB8_Packed` | RGB8 |
| `PixelType_Gvsp_BayerRG8` | Bayer RG 8bit |
| `PixelType_Gvsp_BayerGB8` | Bayer GB 8bit |
| `PixelType_Gvsp_BayerGR8` | Bayer GR 8bit |
| `PixelType_Gvsp_BayerBG8` | Bayer BG 8bit |

## 错误码

返回值为 `0` (`MV_OK`) 表示成功，非零为错误码，格式化为 `0x{ret:08x}` 查看。

## 参考文件

- `camera/MvImport/MvCameraControl_class.py` - 相机控制类，所有API方法
- `camera/MvImport/CameraParams_header.py` - 参数结构体和常量定义
- `camera/MvImport/MvErrorDefine_const.py` - 错误码定义
- `camera/MvImport/PixelType_header.py` - 像素格式定义
