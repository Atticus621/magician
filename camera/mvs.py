# -- coding: utf-8 --
"""MVS相机SDK封装，统一管理DLL加载和API导入。

用法:
    from camera.mvs import *
"""
import sys
import os
import ctypes
from ctypes import *

# 添加MVS DLL搜索路径
os.add_dll_directory(r"C:\Program Files (x86)\Common Files\MVS\Runtime\Win64_x64")
os.environ["PATH"] = r"C:\Program Files (x86)\Common Files\MVS\Runtime\Win64_x64" + ";" + os.environ.get("PATH", "")

# 添加MvImport模块路径
_mvs_dir = os.path.join(os.path.dirname(__file__), "MvImport")
if _mvs_dir not in sys.path:
    sys.path.append(_mvs_dir)

from MvCameraControl_class import *
from CameraParams_header import *
from CameraParams_const import *
from MvErrorDefine_const import *
from PixelType_header import *
from MvCameraControl_class import MvCamCtrldll


def unload_dll():
    """显式卸载MvCameraControl.dll，释放动态库句柄"""
    try:
        handle = MvCamCtrldll._handle
        if handle:
            ctypes.windll.kernel32.FreeLibrary(ctypes.c_void_p(handle))
    except Exception:
        pass
