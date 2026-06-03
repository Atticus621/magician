# DobotDemoForPython64

DobotDemoForPython64 is the demo of python package dynamic library files. It can be used directly by the python function to control Dobot Magician.

This document describes the secondary development environment building and demo python codes, frameworks, and systems, aiming to help secondary developer to understand common API of Dobot Magician and build development environment quickly.

<div align=center>

<img src="images/pythondemo.png" width="500" height="350" />

</div>

## Files Description

- Dll files contain the api functions needed to control Dobot Magician.
- DobotDllType.py : Specific implementing file. This section encapsulate api functions provided by the dll as python function.
- DobotControl.py : Secondary encapsulation of Dobot API. In order to get you up and running quickly, the code in the example adds a certain comment for easy reading.Examples are as follows:

```python
#将dll读取到内存中并获取对应的CDLL实例
#Load Dll and get the CDLL object
api = dType.load()

#建立与dobot的连接
#Connect Dobot
state = dType.ConnectDobot(api, "", 115200)[0]
print("Connect status:",CON_STR[state])
```

## Python API

DobotDllType.py encapsulates the C type interface of Dobot DLL, which is Python API of Dobot. The example for loading DLL is shown as follows.

```PYTHON
def load():
    if platform.system() == "Windows":
        return CDLL("DobotDll.dll",  RTLD_GLOBAL)
    elif platform.system() == "Darwin" :
        return CDLL("libDobotDll.dylib",  RTLD_GLOBAL)
    elif platform.system() == "Linux":
        return cdll.loadLibrary("libDobotDll.so")
```

## Usage

- For Windows OS, please add the DLLs directory to environment variable Path.
- For Linux OS, please add the following statement at the end of `~/.bash_profile` file and restart computer.
```
export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:DOBOT_LIB_PATH
```
- For Mac OS
If the following error occurs, the solution is:
```python
File "/Library/Frameworks/Python.framework/Versions/3.7/lib/python3.7/ctypes/__init__.py", line 356, in __init__
    self._handle = _dlopen(self._name, mode)
OSError: dlopen(libDobotDll.dylib, 10): image not found
```

```
% cd DobotDemoForPython
% otool -L libDobotDll.dylib
```
The executable_path part, all use the tools of `install_name_tool` to modify the path.

```python
# install _name_tool -change <old path> <new path> libDobotDll.dylib
install_name_tool -change @executable_path/QtSerialPort.framework/Versions/5/QtSerialPort /Users/outannexway/Downloads/Dobot/DobotDemoV2.0-20170118/DobotDemoForPython/QtSerialPort.framework/Versions/5/QtSerialPort libDobotDll.dylib
```
- cd DobotDemoForPython
Use vscode debugging, be sure to use the DobotDemoForPython path
- Connect the Dobot Magician
- python DobotControl.py

## Attention

##### There are the following points to note:
- You need to add the DLL address to the system environment variable
- A 32-bit system corresponds to a 32-bit dynamic library, and a 64-bit system corresponds to a 64-bit dynamic library
- please use the python 64 bit environment.
一、Other(其它)
1. dType.dSleep(ms)
描述：用于延迟。
固件版本：After 2.4.0。
参数：ms：毫秒。
返回：无返回值。
2. dType.SetcmdTimeout(api,times)
描述：发往 Dobot控制器的所有指令都带有返回。当由于通信链路干扰等造成指令错误时，控制器将无法识别该条指令且无法返回。因此，每条下发给控制署的指令都有 一个超时时间。
固件版本：After 2.4.0。
参数：#警告# 请保留“api”   变量，不要修改它。
api：Dobot库的对象。
times：毫秒
返回：无返回值。
3. dType.DobotExec(api)
描述：在某些语言中，当调用 API接口后，由于没有事件循环，应用程序将直接退出，因此将导致指令没有下发到 Dobot 控制器中。为了避免这种情况，我们提供了事件循环接口，在应用程序退出前调用（目前已知的需要做此处理的语言有 Python）。
固件版本：After 2.4.0。
参数：#警告# 请保留“api”变量，不要修改它。
api： Dobot库的对象。
返回：无返回值。
二、Pose（位姿）
1. dType.GetPose(api)
描述：获取实时位姿
固件版本：After 2.4.0。
参数：#警告# 请保留“api”变量，不要修改它。
api：Dobot库的对象。
返回：#提示# 有效的返回值都会以队列的形式返回。
list[0]：X轴坐标；list[1]：Y轴坐标；list[2]：Z轴坐标；list[3]： R末端坐标；
list[4]：底座角度；list[5]：大臂角度；list[6]：小臂角度；list[7]：末端角度
三、HOME（零点）
1. dType.SetHOMEParams(api,x, y,z, r,isQueued=0)
描述：设置回零参数。
固件版本：After 2.4.0。
参数：#警告# 请保留“api”变量，不要修改它。
api：Dobot库的对象。
x：X轴坐标；y：Y轴坐标；z：Z轴坐标；r：R末端坐标
#警告# 请务必使用队列模式，以适配当前的固件版本。
isQueued ：队列模式使用开关状态。1:使用队列模式，0:不使用队列模式。
返回：#提示# 有效的返回值都会以队列的形式返回。
list[0]：两种可能的结果。队列模式：队列命令索引；立即模式：0。
2. dType.GetHOMEParams(api)
描述：获取回零参数。
固件版本：After 2.4.0。
参数：#警告# 请保留“api”变量，不要修改它。
api： Dobot库的对象。
返回：#提示# 有效的返回值都会以队列的形式返回。
list[0]：X轴坐标；list[1]：Y轴坐标；list[2]：Z轴坐标；list[3]： R末端坐标。
3. dType.SetHOMECmd(api, temp, isQueued=0)
描述：执行回零功能。
固件版本：After 2.4.0。
参数：#警告# 请保留“api”变量，不要修改它。
api: Dobot库的对象。
temp：无效值。
#警告# 请务必使用队列模式，以适配当前的固件版本。
isQueued：队列模式使用开关状态。1：使用队列模式；0：不使用队列模式。
返回：#提示# 有效的返回值都会以队列的形式返回。
list[0]：两种可能的结果。队列模式：队列命令索引；立即模式：0。
四、EndEffector（末端）
1. dType.SetEndEffectorParams(api, xBias, yBias, zBias, isQueued=0)
描述：设置末端参数。
固件版本：After 2.4.0。
参数：#警告# 请保留“api”变量，不要修改它。
api: Dobot库的对象。
xBias：X轴坐标；yBias：Y轴坐标；zBias：Z轴坐标。
#警告# 请务必使用队列模式，以适配当前的固件版本。
isQueued：队列模式使用开关状态。1：使用队列模式；0：不使用队列模式。
返回：#提示# 有效的返回值都会以队列的形式返回。
list[0]：两种可能的结果。队列命令：队列命令索引；立即命令：0。
2. dType.GetEndEffectorParams(api)
描述：获取当前末端参数。
固件版本：After 2.4.0。
参数：#警告# 请保留“api”变量，不要修改它。
api: Dobot库的对象。
返回：#提示# 有效的返回值都会以队列的形式返回。
list[0]：X轴坐标；list[1]：Y轴坐标；list[2]：Z轴坐标。
3. dType.SetEndEffectorLaser(api, enableCtrl, on, isQueued=0)
描述：设置激光开关。
固件版本：After 2.4.0。
参数：#警告# 请保留“api”变量，不要修改它。
api：Dobot库的对象。
enableCtrl：使能控制。1：Enable；0：Disable。
on：开关状态。1：开；0：关。
#警告# 请务必使用队列模式，以适配当前的固件版本。
isQueued：队列模式使用状态。1：使用队列模式；0：不使用队列模式。
返回：#提示# 有效的返回值都会以队列的形式返回。
list[0]：两种可能的结果。队列模式：队列命令索引；立即模式：0。
4. dType.GetEndEffectorLaser(api)
描述：获取激光开关状态。
固件版本：After 2.4.0。
参数：#警告# 请保留“api”变量，不要修改它。
api：Dobot库的对象。
返回：#提示# 有效的返回值都会以队列的形式返回。
list[0]：两种可能的结果。0：关；1：开。
5. dType.SetEndEffectorSuctionCup(api, enableCtrl, on, isQueued=0)
描述：设置吸盘吸放。
固件版本：After 2.4.0。
参数：#警告# 请保留“api”变量，不要修改它。
api：Dobot库的对象。
enableCtrl：使能控制。1：Enable；0：Disable。
on：开关状态。1：开；0：关。
#警告# 请务必使用队列模式，以适配当前的固件版本。
isQueued：队列模式使用状态。1：使用队列模式；0：不使用队列模式。
返回：#提示# 有效的返回值都会以队列的形式返回。
list[0]：两种可能的结果。队列模式：队列命令索引；立即模式：0。
6. dType.GetEndEffectorSuctionCup(api)
描述：获取吸盘吸放状态。
固件版本：After 2.4.0。
参数：#警告# 请保留“api”变量，不要修改它。
api： Dobot库的对象。
返回：#提示# 有效的返回值都会以队列的形式返回。
list[0]：两种可能的结果。0：关；1：开。
7. dType.SetEndEffectorGripper(api, enableCtrl, on, isQueued=0)
描述：设置爪子抓住/释放。
固件版本：After 2.4.0。
参数：#警告# 请保留“api”变量，不要修改它。
api: Dobot库的对象
enableCtrl：使能控制。1：Enable；0：Disable。
on：开关状态。1：开；0：关。
#警告# 请务必使用队列模式，以适配当前的固件版本。
isQueued：队列模式使用状态。1：使用队列模式；0：不使用队列模式。
返回：#提示# 有效的返回值都会以队列的形式返回。
list[0]：两种可能的结果。队列模式：队列命令索引；立即模式：0。
8. dType.GetEndEffectorGripper(api)
描述：获取爪子夹住状态。
固件版本：After 2.4.0。
参数：#警告# 请保留“api”变量，不要修改它。
api: Dobot库的对象
返回：#提示# 有效的返回值都会以队列的形式返回。
list[0]：两种可能的结果。0：关；1：开。
五、 LostStep
1. dType.SetLostStepParams(api, threshold)
描述：设置丢步参教。
固件版本：After 3.2.2。
参数：#警告# 请保留“api”变量，不要修改它。
api：Dobot库的对象。
threshold：停止命令角度值。
返回：无返回值。
2. dType.SetLostStepCmd(api, isQueued=0)
描述：执行丢步命令。
固件版本：After 3.2.2。
参数：#警告# 请保留“api”变量，不要修改它。
api：The object of Dobot Library。
#警告# 请务必使用队列模式，以适配当前的固件版本。
isQueued：队列模式使用状态。1：使用队列模式；0：不使用队列模式。
返回：#提示# 有效的返回值都会以队列的形式返回。
list[0]：两种可能的结果。队列模式：队列命令索引；立即模式：0。
六、JOG（点动）
1. dType.SetJOGJointParams(api,j1Velocity,j1Acceleration,j2Velocity,j2Acceleration,j3Velocity,j3Acceleration,j4Velocity,j4Acceleration,isQueued=0)
描述：设置关节点动参数。
固件版本：After 2.4.0。
参数：#警告#请保留“api”变量，不要修改它。
api：Dobot库的对象。
j1Velocity：关节1点动最大速度；j1Acceleration：关节1点动最大加速度；j2Velocity：关节2点动最大速度；j2Acceleration：关节2点动最大加速度；j3Velocity：关节3点动最大速度；j3Acceleration：关节3点动最大加速度；j4Velocity：关节4点动最大速度；j4Acceleration：关节4点动最大加速度。
#警告# 请务必使用队列模式，以适配当前的固件版本。
isQueued：队列模式使用状态。1：使用队列模式；0：不使用队列模式。
返回：#提示# 有效的返回值都会以队列的形式返回。
list[0]：两种可能的结果。队列模式：队列命令索引；立即模式：0。
2. dType.GetJOGJointParams(api)
描述：获取关节点动参数。
固件版本：After 2.4.0。
参数：#警告# 请保留“api”变量，不要修改它。
api：Dobot库的对象。
返回：#提示# 有效的返回值都会以队列的形式返回。
list[0]：关节1速度；list[1]：关节1加速度；list[2]：关节2速度；list[3]：关节2加速度；list[4]：关节3速度；list[5]：关节3加速度；list[6]：关节4速度；list[7]：关节4加速度。
3. dType.SetJOGCoordinateParams(api,xVelocity,xAcceleration,yVelocity,yAcceleration,zVelocity,zAcceleration,rVelocity,rAcceleration,isQueued=0)
描述：设置坐标轴点动参数。
固件版本：After 2.4.0。
参数：#警告# 请保留“api”变量，不要修改它。
Api：Dobot库的对象；xVelocity：X速度；xAcceleration：X加速度；yVelocity：Y速度；yAcceleration：Y加速度；zVelocity：Z速度；zAcceleration：Z加速度；rVelocity：R速度：rAcceleration：R加速度。
#警告# 请务必使用队列模式，以适配当前的固件版本。
isQueued：队列模式使用状态。1：使用队列模式；0：不使用队列模式。
返回：#提示# 有效的返回值都会以队列的形式返回。
list[0]：两种可能的结果。队列模式：队列命令索引；立即模式：0。
4. dType.GetJOGCoordinateParams(api)
描述：获取坐标轴点动参数
固件版本：After 2.4.0
参数：#警告# 请保留“api”变量，不要修改它。
api：Dobot库的对象。
返回：#提示# 有效的返回值都会以队列的形式返回。
list[0]：X速度；list[1]：X加速度；list[2]：Y速度；list[3]：Y加速度；list[4]：Z速度；list[5]：Z加速度；list[6]：R速度；list[7]：R加速度。
5. dType.SetJOGCommonParams(api,value_velocityratio,value_accelerationratio,isQueued=0)
描述：设置点动公共参数。
固件版本：After 2.4.0。
参数：#警告# 请保留“api”变量，不要修改它。
api：Dobot库的对象；value_velocityratio：点动速度百分比；value_accelerationratio：点动加速度百分比。
#警告# 请务必使用队列模式，以适配当前的固件版本。
isQueued：队列模式使用开关状态。1：使用队列模式；0：不使用队列模式。
返回：#提示# 有效的返回值都会以队列的形式返回。
list[0]：两种可能的结果。队列模式：队列命令索引；立即模式：0。
6. dType.GetJOGCommonParams(api)
描述：获取点动公共参数。
固件版本：After 2.4.0。
参数：#警告# 请保留“api”变量，不要修改它。
api：Dobot库的对象。
返回：#提示# 有效的返回值都会以队列的形式返回。
list[0]：点动速度百分比；list[1]：点动加速度百分比。
7. dType.SetJOGCmd(api,isJoint, cmd, isQueued=0)
描述：执行点动指令。
固件版本：After 2.4.0。
参数：#警告# 请保留“api”变量，不要修改它。
api：Dobot库的对象。
isJoint：是关节点动还是坐标轴点动。0：Move in cartesian coordinate system；1：Move in jonit coordinate system。
cmd：命令。0：IDEL；1：x+ or joint1+；2：x- or joint1-；3：y+ or joint2+；4：y- or joint2-；5：z+ or joint3+；6：z- or joint3-；7：r+ or joint4+；8：r- or joint4-；9：L+；10：L-
#警告# 请务必使用队列模式，以适配当前的固件版本，滑轨需使用关节模式。isQueued：队列模式使用开关状态。1：使用队列模式；0：不使用队列模式。
返回：#提示# 有效的返回值都会以队列的形式返回。
list[0]：两种可能的结果。队列模式：队列命令索引；立即模式：0。
七、PTP（运动）
1. dType.SetPTPJointParams(api, j1Velocity, j1Acceleration, j2Velocity, j2Acceleration, j3Velocity, j3Acceleration, j4Velocity, j4Acceleration, isQueued=0)
描述：设置关节点位参数。
固件版本：After 2.4.0。
参数：#警告# 请保留“api”变量，不要修改它。
api：Dobot库的对象。
j1Velocity：关节1速度；j1Acceleration：关节1加速度；j2Velocity:关节2速度；j2Acceleration：关节2加速度；j3Velocity：关节3速度；j3Acceleration :关节3加速度；j4Velocity：关节4速度；j4Acceleration：关节4加速度。
#警告# 请务必使用队列模式，以适配当前的固件版本。
isQueued：队列模式使用开关状态。1：使用队列模式；0：不使用队列模式。
返回：#提示# 有效的返回值都会以队列的形式返回。
list[0]：两种可能的结果。队列模式：队列命令索引；立即模式：0。
2. dType.GetPTPJointParams(api)
描述：获取关节点位参数。
固件版本：After 2.4.0。
参数：#警告# 请保留“api”变量，不要修改它。
api：Dobot库的对象。
返回：#提示# 有效的返回值都会以队列的形式返回。
list[0]：关节1速度；list[1]：关节1加速度；list[2]：关节2速度；list[3]：关节2加速度；list[4]：关节3速度；list[5]：关节3加速度；list[6]：关节4速度；list[7]：关节4加速度。
3. dType.SetPTPCoordinateParams(api, xyzVelocity, xyzAcceleration, rVelocity, rAcceleration, isQueued=0)
描述：设置坐标轴点位参数。
固件版本：After 2.4.0。
参教：#警告# 请保留“api”变量，不要修改它。
api：Dobot库的对象。
xyzVelocity：XYZ坐标轴速度；xyzAcceleration：XYZ坐标轴加速度；rVelocity：R末端速度；rAcceleration：R末端加速度。
#警告# 请务必使用队列模式，以适配当前的固件版本。
isQueued：队列模式使用开关状态。1：使用队列模式；0：不使用队列模式。
返回：#提示# 有效的返回值都会以队列的形式返回。
list[0]：两种可能的结果。队列模式：队列命令索引；立即模式：0。
4. dType.GetPTPCoordinateParams(api)
描述：获取坐标轴点位参数。
固件版本：After 2.4.0。
参数：#警告# 请保留“api”变量，不要修改它。
api：Dobot 库的对象。
返回：#提示# 有效的返回值都会以队列的形式返回。
list[0]：XYZ坐标轴速度；list[1]：XYZ坐标轴加速度；list[2]： R末端速度；list[3]： R末端加速度。
5. dType.SetPTPJumpParams(api,jumpHeight, zLimit, isQueued=0)
描述：设置门型模式点位参数。
固件版本：After 2.4.0。
参数：#警告# 请保留“api”变量，不要修改它。
api：Dobot 库的对象。
jumpHeight：门型运动模式时抬升高度；zLimit：抬升的最大高度。
#警告# 请务必使用队列模式，以适配当前的固件版本。
isQueued：队列模式使用开关状态。1：使用队列模式；0：不使用队列模式。
返回：#提示# 有效的返回值都会以队列的形式返回。
list[0]：两种可能的结果。队列模式：队列命令索引；立即模式：0。
6. dType.GetPTPJumpParams(api)
描述：获取门型模式点位参数。
固件版本：After 2.4.0。
参数：#警告# 请保留“api”变量，不要修改它。
api：Dobot 库的对象。
返回：#提示# 有效的返回值都会以队列的形式返回。
list[0]：门型运动模式时抬升高度；list[1]：抬升的最大高度。
7. dType.SetPTPCommonParams(api, velocityratio, accelerationratio, isQueued=0)
描述：设置点位公共参数。
固件版本：After 2.4.0。
参数：#警告# 请保留“api”变量，不要修改它。
api：Dobot 库的对象。
Velocityratio：PTP运动速度比例；accelerationratio：PTP运动加速度比例。
#警告# 请务必使用队列模式，以适配当前的固件版本。
isQueued：队列模式使用开关状态。1：使用队列模式；0：不使用队列模式。
返回：#提示# 有效的返回值都会以队列的形式返回。
list[0]：两种可能的结果。队列模式：队列命令索引；立即模式：0。
8. dType.GetPTPCommonParams(api)
描述：获取点位速度参数。
固件版本：After 2.4.0。
参数：#警告# 请保留“api”变量，不要修改它。
api：Dobot库的对象。
返回：#提示# 有效的返回值都会以队列的形式返回。
list[0]：PTP运动速度比例；list[1]：PTP运动加速度比例。
9. dType.SetPTPCmd(api, ptpMode, x, y, z, rHead, isQueued=0)
描述：执行PTP运动指令。
固件版本：After 2.4.0。
参数：#警告# 请保留“api”变量，不要修改它。
ptpMode：ptp运动模式。0：基于绝对位置的笛卡尔坐标系下的关节门形运动模式；1：基于绝对位置的笛卡尔坐标系下的关节运动模式；2：基于绝对位置的笛卡尔坐标系下的直线运动模式；3：基于绝对位置的关节坐标系下的门形运动模式；4：基于绝对位置的关节坐标系下的关节运动模式；5：基于绝对位置的关节坐标系下的直线运动模式；6：基于相对位置的关节坐标系下的关节模式；7：基于相对位置的笛卡尔坐标系下的直线运动模式；8：基于相对位置的笛卡尔坐标系下的关节模式。9：基于绝对位置的笛卡尔坐标系统下的线性门形运动模式。.
x：位置值1；y：位置值2；z：位置值3；rHead：位置值4。
#警告# 请务必使用队列模式，以适配当前的固件版本。
isQueued：队列模式使用开关状态。1：使用队列模式；0：不使用队列模式。
返回：#提示# 有效的返回值都会以队列的形式返回。
list[0]：两种可能的结果。队列模式：队列命令索引；立即模式：0。
八、ARC（圆弧）
1. dType.SetARCParams(api, xyzVelocity, rVelocity, xyzAcceleration, rAcceleration, isQueued=0)
描述：设置圆弧插补功能参数。
固件版本：After 2.4.0
参教：#警告# 请保留“api”变量，不要修改它。
api：Dobot 库的对象。
xyzVelocity：xyz坐标轴速度；rVelocity：r末端旋转速度；xyzAcceleration：xyz坐标轴加速度；rAcceleration：r末端旋转加速度
#警告# 请务必使用队列模式，以适配当前的固件版本。
isQueued：队列模式使用开关状态。1：使用队列模式；0：不使用队列模式。
返回：#提示# 有效的返回值都会以队列的形式返回。
list[0]：两种可能的结果。队列模式：队列命令索引；立即模式：0。
2. dType.GetARCParams(api)
描述：获取圆弧插补功能参数。
固件版本：After 2.4.0。
参数：#警告# 请保留“api”变量，不要修改它。
api：Dobot 库的对象。
返回：#提示# 有效的返回值都会以队列的形式返回。
list[0]：xyz坐标轴速度；list[1]：xyz坐标轴加速度；list[2]：末端旋转速度；list[3]:末端旋转加速度。
3. dType.SetARCCmd(api, cirPoint, toPoint,isQueued=0)
描述：执行圆弧插补功能。
固件版本：After 2.4.0。
参数：#警告# 请保留“api”变量，不要修改它。
api：Dobot 库的对象。
cirPoint：过渡点的数值列表。cirPoint[0]：x；cirPoint[1]：y；cirPoint[2]：z；cirPoint[3]：r。
toPoint：目标点的数值列表。toPoint[0]：x；toPoint[1]：y；toPoint[2]：z；toPoint[3]：r。
#警告# 请务必使用队列模式，以适配当前的固件版本。
isQueued：队列模式使用开关状态。1：使用队列模式；0：不使用队列模式。
返回：#提示# 有效的返回值都会以队列的形式返回。
list[0]：两种可能的结果。队列模式：队列命令索引；立即模式：0。
4. dType.SetCircleCmd(api, cirPoint, toPoint, count, isQueued=0)
描述：执行整圆指令。
固件版本：大于 2.4.0。
参数：#警告# 请保留“api”变量，不要修改它。
api：Dobot 库的对象。
cirPoint：过渡点的数值列表。cirPoint[0]：x；cirPoint[1]：y；cirPoint[2]：z；cirPoint[3]：r。
toPoint：目标点的数值列表。toPoint[0]：x；toPoint[1]：y；toPoint[2]：z；toPoint[3]：r。
count：圈数。
#警告# 请务必使用队列模式，以适配当前的固件版本。
isQueued：队列模式使用开关状态。1：使用队列模式；0：不使用队列模式。
返回：#提示# 有效的返回值都会以队列的形式返回。
list[0]：两种可能的结果。队列模式：队列命令索引；立即模式：0。
九、WAIT（延时）
1. dType.SetWAITCmd(api, waitTime, isQueued=0)
描述：执行时间等待功能。
固件版本：After 2.4.0。
参数：#警告# 请保留“api”变量，不要修改它。
api：Dobot 库的对象。
waitTime:毫秒。
#警告# 请务必使用队列模式，以适配当前的固件版本。
isQueued：队列模式使用开关状态。1：使用队列模式；0：不使用队列模式。
返回：#提示# 有效的返回值都会以队列的形式返回。
list[0]：两种可能的结果。队列模式：队列命令索引；立即模式：0。
九、EIO（I/O）
1. dType.SetIOMultiplexing(api, address, multiplex, isQueued=0)
描述：设置 I/O 复用。
固件版本：After 2.4.0。
参数：#警告# 请保留“api”变量，不要修改它。
api：Dobot库的对象。
#提示# 根据Magician硬件版本有不同的参数设置，详情参照说明书。
address：EIO地址。
multiplex：EIO配置类型。0：Dummy；1：OUTPUT；2：PWM；3：INPUT；4：AD；5：DIPU；6：DIPD。
#警告# 请务必使用队列模式，以适配当前的固件版本。
isQueued：队列模式使用开关状态。1：使用队列模式；0：不使用队列模式。
返回：#提示# 有效的返回值都会以队列的形式返回。
list[0]：两种可能的结果。队列模式：队列命令索引；立即模式：0。
2. dType.GetIOMultiplexing(api, addr)
描述：读取 I/O 复用。
固件版本：After 2.4.0。
参数：#警告# 请保留“api”变量，不要修改它。
api：Dobot 库的对象。
#提示# 根据Magician硬件版本有不同的参数设置，详情参照说明书。
addr：IO地址。
返回：#提示# 有效的返回值都会以队列的形式返回。
list[0]：EIO的配置类型。0：Dummy；1：OUTPUT；2：PWM；3：INPUT；4：AD；5：DIPU；6：DIPD。
3. dType.SetIODO(api, address, level, isQueued=0)
描述：设置 I/O输出电平。
固件版本：After 2.4.0。
参数：#警告# 请保留“api”变量，不要修改它。
api：Dobot 库的对象。
#提示# 根据Magician硬件版本有不同的参数设置，详情参照说明书。
address：EIO地址。
level：电平。0：低电平；1：高电平。
#警告# 请务必使用队列模式，以适配当前的固件版本。
isQueued：队列模式使用开关状态。1：使用队列模式；0：不使用队列模式。
返回：#提示# 有效的返回值都会以队列的形式返回。
list[0]：两种可能的结果。队列模式：队列命令索引；立即模式：0。
4. dType.GetIODO(api, addr)
描述：读取 I/O 输出电平。
固件版本：After 2.4.0。
参数：#警告# 请保留“api”变量，不要修改它。
api：Dobot 库的对象。
#提示# 根据Magician件版本有不同的参数设置，详情参照说明书。
addr：EIO地址。
返回：#提示# 有效的返回值都会以队列的形式返回。
list[0]：I/O 输出电平。0：低电平；1：高电平。
5. dType.SetIOPWM(api, address, frequency, dutyCycle, isQueued=0)
描述：设置 I/O PWM 输出。
固件版本：After 2.4.0。
参数：#警告# 请保留“api”变量，不要修改它。
api：Dobot库的对象。
#提示# 根据Magician硬件版本有不同的参数设置，详情参照说明书。
address：EIO地址；frequency：频率；dutyCycle：占空比。
#警告# 请务必使用队列模式，以适配当前的固件版本。
isQueued：队列模式使用开关状态。1：使用队列模式；0：不使用队列模式。
返回：#提示# 有效的返回值都会以队列的形式返回。
list[0]：两种可能的结果。队列模式：队列命令索引；立即模式：0。
6. dType.GetIOPWM(api, addr)
描述：读取 I/O PWM输出。
固件版本：After 2.4.0。
参数：#警告# 请保留“api”变量，不要修改它。
api：Dobot库的对象。
#提示# 根据Magician硬件版本有不同的参数设置，详情参照说明书。
addr：EIO地址。
返回：#提示# 有效的返回值都会以队列的形式返回。
list[0]：PWM频率；PWM占空比。
7. dType.GetIODl(api, addr)
描述：读取 I/O输入电平。
固件版本：After 2.4.0。
参数：#警告# 请保留“api”变量，不要修改它。
api：Dobot库的的对象。
#提示# 根据Magician硬件版本有不同的参数设置，详情参照说明书。
addr：EIO地址。
返回：#提示# 有效的返回值都会以队列的形式返回。
list[0]：电平。0：低电平；1：高电平。
8. dType.SetEMotor(api, index, isEnabled, speed, isQueued=0)
描述：设置电机开关。
固件版本：After 2.4.0。
参数：#警告# 请保留“api”变量，不要修改它。
api：Dobot库的的对象。
index：电机编号。0：电机1；1：电机2。
isEnabled：开关状态。0：关；1：开。
speed：运转速度。
#警告# 请务必使用队列模式，以适配当前的固件版本。
isQueued：队列模式使用开关状态。1：使用队列模式；0：不使用队列模式。
返回：#提示# 有效的返回值都会以队列的形式返回。
list[0]：两种可能的结果。队列模式：队列命令索引；立即模式：0。
9. dType.SetEMotorS(api, index, isEnabled, speed, distance, isQueued=0)
描述：设置电机速度和移动距离。
固件版本：After 2.4.0。
参数：#警告# 请保留“api”变量，不要修改它。
api：Dobot库的的对象。
index：电机编号。0：电机1；1：电机2。
isEnabled：开关状态。0：关；1：开。
speed：运转速度；distance：运动距离。
#警告# 请务必使用队列模式，以适配当前的固件版本。
isQueued：队列模式使用开关状态。1：使用队列模式；0：不使用队列模式。
返回：#提示# 有效的返回值都会以队列的形式返回。
list[0]：两种可能的结果。队列模式：队列命令索引；立即模式：0。
10. dType.GetIOADC(api, addr)
描述：读取 I/O 模数转换值。
参数：#警告# 请保留“api”变量，不要修改它。
api：Dobot库的的对象。
addr：EIO地址。
返回：#提示# 有效的返回值都会以队列的形式返回。
list[0]：模数转换值。
十、Sensors（传感器）
1. dType.SetColorSensor(api,isEnable, colorPort, version=0)
描述：此功能用于控制颜色传感器开关状态。
固件版本：After 3.6.6。
参数：#警告# 请保留“api”变量，不要修改它。
api：Dobot库的的对象。
isEnable：开关状态。1：开；2：关。
#提示# 请根据颜色传感器的版本设置参数，具体参考说明书。
version颜色传感器版本号，默认值是0。
返回：无返回值。
2. dType.GetDeviceWithL(api)
描述：此功能用于获取滑轨的开关状态。
固件版本：After 3.2.2。
参数：#警告# 请保留“api”变量，不要修改它。
api：Dobot库的的对象。
返回：#提示# 有效的返回值都会以队列的形式返回。
#Tip# Using RGB color model。
list[0]：红色值；list[1]：绿色值；list[2]：蓝色值。
3. dType.SetlnfraredSensor(api, isEnable, infraredPort, version=0)
描述：设置光电传感器的端口号和状态。
固件版本：After 3.6.6。
参数：#警告# 请保留“api”变量，不要修改它。
api：Dobot库的的对象。
isEnable：开关状态。0：关；1：开。
infraredPort：光电传感器端口号(0-3)。
#提示# 请根据光电传感器的版本设置参数，具体参考说明书。
version光电传感器版本号，默认值是0。
返回：无返回值。
4. dType.GetInfraredSensor(api, infraredPort)
描述：获取红外传感器。
固件版本：After 3.2.2。
参数：#警告# 请保留“api”变量，不要修改它。
api：Dobot库的的对象。
infraredPort：光电传感器端口号(0-3)。
返回：#提示# 有效的返回值都会以队列的形式返回。
list[0]：红外传感器。0：无触发；1：有触发。
十一、LinearRail（滑轨）
1. dType.SetDeviceWithL(api, isWithL, version=0)
描述：此功能用于控制滑轨的开关。
固件版本：After 3.6.6。
参数：#警告# 请保留“api”变量，不要修改它。
api：Dobot库的的对象。
isWithL：开关状态。1：开；0：关。
#提示# 请根据滑轨版本设置参数，详情参见用户说明书。
version：滑执版本号，默认值是0。
返回：无返回值。
2. dType.GetDeviceWithL(api)
描述：此功能用于获取滑轨的开关状态。
固件版本：After 3.0.0。
参数：#警告# 请保留“api”变量，不要修改它。
api：Dobot库的的对象。
返回：#提示# 有效的返回值都会以队列的形式返回。
list[0]：滑轨的两种开关状态。1：开；0：关。
3. dType.GetPoseL(api)
描述：此功能用于获取当前滑轨位置。
固件版本：After 3.0.0。
参数：#警告# 请保留“api”变量，不要修改它。
api：Dobot库的的对象。
返回：返回：#提示# 有效的返回值都会以队列的形式返回。
list[0]：滑轨的实时位姿。
4. dType.SetJOGLParams(api,velocity, acceleration, isQueued=0)
描述：此功能用于设置滑轨点动参数。
固件版本：After 3.0.0。
参数：#警告# 请保留“api”变量，不要修改它。
api：Dobot库的的对象。
velocity：点动最大速度；acceleration：点动最大加速度。
#警告# 请务必使用队列模式，以适配当前的固件版本。
isQueued：队列模式使用开关状态。1：使用队列模式；0：不使用队列模式。
返回：#提示# 有效的返回值都会以队列的形式返回。
list[0]：两种可能的结果。队列模式：队列命令索引；立即模式：0。
5. dType.GetJOGLParams(api)
描述：此功能用于获取滑轨点动参数。
固件版本：After 3.0.0。
参数：#警告# 请保留“api”变量，不要修改它。
api：Dobot库的的对象。
返回：#提示# 有效的返回值都会以队列的形式返回。
list[0]：点动最大速度。
list[1]：点动最大加速度。
6. dType.SetPTPLParams(api,velocity, acceleration, isQueued=0)
描述：此功能用于设置滑轨点位参数。
固件版本：After 3.0.0。
参数：#警告# 请保留“api”变量，不要修改它。
api：Dobot库的的对象。
velocity：点动最大速度；acceleration：点动最大加速度。
#警告# 请务必使用队列模式，以适配当前的固件版本。
isQueued：队列模式使用开关状态。1：使用队列模式；0：不使用队列模式。
返回：#提示# 有效的返回值都会以队列的形式返回。
list[0]：两种可能的结果。队列模式：队列命令索引；立即模式：0。
7. dType.GetPTPLParams(api)
描述：此功能用于获取滑轨点位参数。
固件版本：After 3.0.0。
参数：#警告# 请保留“api”变量，不要修改它。
api：Dobot库的的对象。
返回：#提示# 有效的返回值都会以队列的形式返回。
list[0]：点动最大速度；list[1]：点动最大加速度。
8. dType.SetPTPWithLCmd(api, ptpMode, x, y, z, rHead,I, isQueued=0)
描述：此功能用于执行滑轨点动。
固件版本：After 3.0.0。
参数：#警告# 请保留“api”变量，不要修改它。
api：Dobot库的的对象。
ptpMode：ptp运动模式。0：基于绝对位置的笛卡尔坐标系下的关节门形运动模式；1：基于绝对位置的笛卡尔坐标系下的关节运动模式；2：基于绝对位置的笛卡尔坐标系下的直线运动模式；3：基于绝对位置的关节坐标系下的门形运动模式；4：基于绝对位置的关节坐标系下的关节运动模式；5：基于绝对位置的关节坐标系下的直线运动模式；6：基于相对位置的关节坐标系下的关节模式；7：基于相对位置的笛卡尔坐标系下的直线运动模式；8：基于相对位置的笛卡尔坐标系下的关节模式。9：基于绝对位置的笛卡尔坐标系统下的线性门形运动模式。
x：x值；y：y值；z：z值；rHead：末端角度；I：位置的线性轨道值。
#警告# 请务必使用队列模式，以适配当前的固件版本。
isQueued：队列模式使用开关状态。1：使用队列模式；0：不使用队列模式。
返回：#提示# 有效的返回值都会以队列的形式返回。
list[0]：两种可能的结果。队列模式：队列命令索引；立即模式：0。


