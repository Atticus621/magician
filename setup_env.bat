@echo off
REM ============================================
REM 人工智能分拣系统 - Conda环境配置脚本
REM ============================================

echo [1/3] 创建 conda 环境 B (Python 3.10)...
conda create -n B python=3.10 -y

echo [2/3] 激活环境并安装依赖...
call conda activate B
pip install -r requirements.txt

echo [3/3] 验证安装...
python -c "import cv2; print('OpenCV:', cv2.__version__)"
python -c "import numpy; print('NumPy:', numpy.__version__)"
python -c "import tkinter; print('tkinter: OK')"

echo.
echo ============================================
echo 环境配置完成！
echo 运行方式:
echo   conda activate B
echo   python main.py
echo ============================================
pause
