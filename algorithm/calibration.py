# -- coding: utf-8 --
import cv2
import numpy as np
import xml.etree.ElementTree as ET


def load_calibration_xml(xml_path):
    """
    从标定XML文件中读取标定矩阵和标定点对。

    XML文件由标定软件生成，已包含最小二乘法计算好的透视变换矩阵，
    考虑了旋转、缩放、纵横比、倾斜、透射等因素。

    参数:
        xml_path: XML文件路径

    返回:
        H: 3x3 单应性矩阵（numpy array），将图像坐标转换为物理坐标
        img_points: 图像坐标点列表 shape (N, 2)
        world_points: 物理坐标点列表 shape (N, 2)
        info: dict，包含标定误差等附加信息
    """
    tree = ET.parse(xml_path)
    root = tree.getroot()

    # 读取标定矩阵 (CalibOutputParam -> CalibMatrix)
    calib_matrix_node = root.find('.//CalibOutputParam/CalibFloatListParam[@ParamName="CalibMatrix"]')
    if calib_matrix_node is None:
        raise ValueError("XML文件中未找到CalibMatrix")

    values = [float(v.text) for v in calib_matrix_node.findall('ParamValue')]
    if len(values) != 9:
        raise ValueError(f"CalibMatrix应包含9个值，实际为{len(values)}个")

    H = np.array(values, dtype=np.float64).reshape(3, 3)

    # 读取图像坐标点
    img_node = root.find('.//CalibInputParam/CalibPointFListParam[@ParamName="ImagePointLst"]')
    img_points = []
    if img_node is not None:
        for pt in img_node.findall('PointF'):
            x = float(pt.find('X').text)
            y = float(pt.find('Y').text)
            img_points.append([x, y])

    # 读取物理坐标点
    world_node = root.find('.//CalibInputParam/CalibPointFListParam[@ParamName="WorldPointLst"]')
    world_points = []
    if world_node is not None:
        for pt in world_node.findall('PointF'):
            x = float(pt.find('X').text)
            y = float(pt.find('Y').text)
            world_points.append([x, y])

    # 读取附加信息
    info = {}
    for param in root.findall('.//CalibInputParam/CalibParam'):
        name = param.get('ParamName')
        dtype = param.get('DataType')
        val = param.find('ParamValue').text
        if dtype == 'float':
            info[name] = float(val)
        elif dtype == 'int':
            info[name] = int(val)
        else:
            info[name] = val

    return H, np.array(img_points), np.array(world_points), info


def phys_length_to_pixels(H, phys_length_mm, direction='x'):
    """将物理长度(mm)转换为图像像素长度。

    利用标定矩阵的逆矩阵，将物理坐标系中的长度映射回图像坐标系。
    已考虑透视、旋转、伸缩、倾斜等因素。

    参数:
        H: 3x3 单应性矩阵（图像→物理）
        phys_length_mm: 物理长度(mm)
        direction: 'x' 或 'y'，测量方向

    返回:
        pixel_length: 对应的像素长度
    """
    # 计算逆矩阵（物理→图像）
    H_inv = np.linalg.inv(H)

    # 取两个物理点（相距 phys_length_mm）
    if direction == 'x':
        pt1_phys = np.array([0, 0, 1.0])
        pt2_phys = np.array([phys_length_mm, 0, 1.0])
    else:
        pt1_phys = np.array([0, 0, 1.0])
        pt2_phys = np.array([0, phys_length_mm, 1.0])

    # 变换到图像坐标
    pt1_img = H_inv @ pt1_phys
    pt1_img /= pt1_img[2]

    pt2_img = H_inv @ pt2_phys
    pt2_img /= pt2_img[2]

    # 计算像素距离
    pixel_length = np.sqrt((pt2_img[0] - pt1_img[0])**2 + (pt2_img[1] - pt1_img[1])**2)

    return abs(pixel_length)


def pixels_to_phys_length(H, pixel_length, direction='x'):
    """将图像像素长度转换为物理长度(mm)。

    利用标定矩阵，将图像坐标系中的长度映射到物理坐标系。
    已考虑透视、旋转、伸缩、倾斜等因素。

    参数:
        H: 3x3 单应性矩阵（图像→物理）
        pixel_length: 像素长度
        direction: 'x' 或 'y'，测量方向

    返回:
        phys_length_mm: 对应的物理长度(mm)
    """
    # 取两个图像点（相距 pixel_length）
    if direction == 'x':
        pt1_img = np.array([0, 0, 1.0])
        pt2_img = np.array([pixel_length, 0, 1.0])
    else:
        pt1_img = np.array([0, 0, 1.0])
        pt2_img = np.array([0, pixel_length, 1.0])

    # 变换到物理坐标
    pt1_phys = H @ pt1_img
    pt1_phys /= pt1_phys[2]

    pt2_phys = H @ pt2_img
    pt2_phys /= pt2_phys[2]

    # 计算物理距离
    phys_length = np.sqrt((pt2_phys[0] - pt1_phys[0])**2 + (pt2_phys[1] - pt1_phys[1])**2)

    return abs(phys_length)


def get_pixel_precision(info):
    """从标定信息中获取像素精度(mm/pixel)。

    参数:
        info: load_calibration_xml 返回的 info 字典

    返回:
        dict: {
            "x": PixelPrecisionX,
            "y": PixelPrecisionY,
            "avg": PixelPrecision
        }
    """
    return {
        "x": info.get("PixelPrecisionX", 0.1),
        "y": info.get("PixelPrecisionY", 0.1),
        "avg": info.get("PixelPrecision", 0.1),
    }


def load_calibration_txt(txt_path):
    """
    从标定TXT文件读取图像坐标和物理坐标点对。

    TXT文件每行格式: image_x  image_y  world_x  world_y  rotation
    各列以空格/制表符分隔。

    参数:
        txt_path: TXT文件路径

    返回:
        img_points: 图像坐标点数组 shape (N, 2)
        world_points: 物理坐标点数组 shape (N, 2)
    """
    data = np.loadtxt(txt_path)
    if data.ndim != 2 or data.shape[1] < 4:
        raise ValueError("TXT文件格式错误，每行至少需要4列: image_x image_y world_x world_y")
    return data[:, 0:2], data[:, 2:4]


def find_chessboard_corners(img, pattern_size=(4, 4)):
    """检测黑白棋盘格角点，按从上到下、从左到右顺序返回坐标。

    Args:
        img: BGR图像或灰度图
        pattern_size: 棋盘格内角点数 (列, 行)

    Returns:
        corners: numpy数组 shape (N, 2)，按行优先排列；检测失败返回 None
    """
    if img.ndim == 3:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    else:
        gray = img

    ret, corners = cv2.findChessboardCorners(gray, pattern_size,
                                             flags=(cv2.CALIB_CB_ADAPTIVE_THRESH
                                                    | cv2.CALIB_CB_NORMALIZE_IMAGE
                                                    | cv2.CALIB_CB_FAST_CHECK))
    if not ret:
        return None

    # 亚像素精化
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)
    corners = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), criteria)

    # 按从上到下、从左到右排序（左上角为零点）
    pts = corners.reshape(-1, 2)
    # 先按 y 排序分组到行，每行内按 x 排序
    order = np.lexsort((pts[:, 0], pts[:, 1]))
    return pts[order]

def compute_calibration_matrix(img_points, phys_points):
    """
    根据图像坐标点和对应的物理坐标点，计算标定转换矩阵（单应性矩阵）。

    该矩阵将图像坐标映射到物理坐标，涵盖：
    - 缩放（scale）
    - 旋转（rotation）
    - 纵横比（aspect ratio）
    - 倾斜（skew）
    - 平移（translation）
    - 透射/透视（perspective）

    参数:
        img_points:  图像坐标点列表，形状 (N, 2)，N >= 4
                     例如: [[u1, v1], [u2, v2], ...]
        phys_points: 对应的物理坐标点列表，形状 (N, 2)
                     例如: [[x1, y1], [x2, y2], ...]

    返回:
        H: 3x3 单应性矩阵（numpy array），将图像坐标转换为物理坐标

    使用示例:
        # 定义标定点对
        img_pts  = [[100, 150], [300, 150], [300, 350], [100, 350]]
        phys_pts = [[  0,   0], [ 50,   0], [ 50,  50], [  0,  50]]

        H = compute_calibration_matrix(img_pts, phys_pts)

        # 用 H 转换任意图像坐标
        new_img_pt = np.array([200, 250, 1])  # 齐次坐标
        phys_pt = H @ new_img_pt
        phys_pt /= phys_pt[2]  # 归一化
        print(f"物理坐标: ({phys_pt[0]:.2f}, {phys_pt[1]:.2f})")
    """
    img_pts = np.array(img_points, dtype=np.float64)
    phys_pts = np.array(phys_points, dtype=np.float64)

    if img_pts.shape[0] < 4:
        raise ValueError("至少需要4组对应点来计算透视变换矩阵")
    if img_pts.shape != phys_pts.shape:
        raise ValueError("图像坐标点和物理坐标点数量必须一致")

    # 使用 RANSAC 估计单应性矩阵，自动剔除离群点
    H, mask = cv2.findHomography(img_pts, phys_pts, cv2.RANSAC, 5.0)

    if H is None:
        raise RuntimeError("单应性矩阵计算失败，请检查输入点对")

    return H


def apply_transform(H, point):
    """
    使用标定矩阵将单个图像坐标转换为物理坐标。

    参数:
        H:     3x3 单应性矩阵
        point: 图像坐标 (u, v)

    返回:
        (x, y): 物理坐标
    """
    p = np.array([point[0], point[1], 1.0], dtype=np.float64)
    result = H @ p
    result /= result[2]
    return (result[0], result[1])


def apply_transform_batch(H, points):
    """
    使用标定矩阵批量转换图像坐标到物理坐标。

    参数:
        H:      3x3 单应性矩阵
        points: 图像坐标列表，形状 (N, 2)

    返回:
        物理坐标数组，形状 (N, 2)
    """
    pts = np.array(points, dtype=np.float64)
    # 转为齐次坐标 (N, 3)
    ones = np.ones((pts.shape[0], 1))
    pts_h = np.hstack([pts, ones])
    # 矩阵乘法并归一化
    result = (H @ pts_h.T).T
    result /= result[:, 2:3]
    return result[:, :2]


def compute_reprojection_error(H, img_points, phys_points):
    """
    计算标定的重投影误差，用于评估标定精度。

    返回:
        平均误差（物理坐标单位）
    """
    predicted = apply_transform_batch(H, img_points)
    actual = np.array(phys_points, dtype=np.float64)
    errors = np.linalg.norm(predicted - actual, axis=1)
    return np.mean(errors)


class Calibrator:
    """封装标定矩阵的计算和坐标转换。"""

    def __init__(self):
        self._H = None
        self._info = {}
        self._pixels_per_mm = 10.0  # 默认值

    def calibrate(self, img_points, phys_points):
        """根据图像-物理坐标对计算标定矩阵。"""
        self._H = compute_calibration_matrix(img_points, phys_points)
        return self._H is not None

    def load_from_xml(self, xml_path):
        """从标定XML文件加载标定矩阵。

        Args:
            xml_path: XML文件路径

        Returns:
            bool: 加载是否成功
        """
        try:
            self._H, _, _, self._info = load_calibration_xml(xml_path)
            # 从XML计算 pixels_per_mm
            # PixelPrecision 是 mm/pixel，取倒数得 pixels/mm
            pixel_precision = self._info.get("PixelPrecision", 0.1)
            if pixel_precision > 0:
                self._pixels_per_mm = 1.0 / pixel_precision
            return True
        except Exception as e:
            self._H = None
            return False

    def img_to_phys(self, point):
        """将单个图像坐标转换为物理坐标。返回 (x, y) 或 None。"""
        if self._H is None:
            return None
        return apply_transform(self._H, point)

    def img_to_phys_batch(self, points):
        """批量转换图像坐标到物理坐标。"""
        if self._H is None:
            return None
        return apply_transform_batch(self._H, points)

    @property
    def is_calibrated(self):
        return self._H is not None

    @property
    def info(self):
        return self._info

    @property
    def pixels_per_mm(self):
        """从标定文件计算的 pixels/mm 比例。"""
        return self._pixels_per_mm

    @property
    def mm_per_pixel(self):
        """从标定文件计算的 mm/pixel 比例。"""
        return 1.0 / self._pixels_per_mm if self._pixels_per_mm > 0 else 0.1


if __name__ == "__main__":
    # 示例：4个标定点
    img_pts = [
        [100, 150],
        [400, 150],
        [400, 350],
        [100, 350],
    ]
    phys_pts = [
        [  0,   0],
        [ 60,   0],
        [ 60,  40],
        [  0,  40],
    ]

    H = compute_calibration_matrix(img_pts, phys_pts)
    print("标定矩阵 H:")
    print(H)

    err = compute_reprojection_error(H, img_pts, phys_pts)
    print(f"\n平均重投影误差: {err:.4f}")

    # 测试转换
    test_point = [250, 250]
    result = apply_transform(H, test_point)
    print(f"\n图像坐标 {test_point} -> 物理坐标 ({result[0]:.2f}, {result[1]:.2f})")
