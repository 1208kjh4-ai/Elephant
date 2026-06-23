# -*- coding: utf-8 -*-
import os
import Rhino
import Rhino.Geometry as rg
import Rhino.Display as rd
import Rhino.UI
import Eto.Forms as forms
import Eto.Drawing as drawing
import rhinoscriptsyntax as rs
import System
import math

# --- [경로 및 설정] ---
SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
ICON_DIR = os.path.join(SCRIPT_DIR, "icons")
IMG_ARROW = "arrow.png"
IMG_SYMBOL = "symbol.png"
IMG_TEXT = "text.png"

def get_icon(file_name):
    """icons 폴더 내의 PNG 파일을 불러와 Bitmap으로 변환합니다."""
    try:
        if not file_name: return None
        path = os.path.join(ICON_DIR, file_name)
        if os.path.exists(path):
            return drawing.Bitmap(path)
        return None
    except Exception as e:
        print("Icon Error:", e)
        return None

# ==============================================================================
# [1. 통합 지오메트리 엔진]
# ==============================================================================
class MarkGenerator:
    W, H = 1000, 3000
    DIGIT_DB = {
        '0': [[rg.Point3d(750.0,550.0,0), rg.Point3d(750.0,2450.0,0), rg.Point3d(734.9,2535.5,0), rg.Point3d(691.5,2610.7,0), rg.Point3d(625.0,2666.5,0), rg.Point3d(543.4,2696.2,0), rg.Point3d(456.6,2696.2,0), rg.Point3d(375.0,2666.5,0), rg.Point3d(308.5,2610.7,0), rg.Point3d(265.1,2535.5,0), rg.Point3d(250.0,2450.0,0), rg.Point3d(250.0,550.0,0), rg.Point3d(265.1,464.5,0), rg.Point3d(308.5,389.3,0), rg.Point3d(375.0,333.5,0), rg.Point3d(456.6,303.8,0), rg.Point3d(543.4,303.8,0), rg.Point3d(625.0,333.5,0), rg.Point3d(691.5,389.3,0), rg.Point3d(734.9,464.5,0), rg.Point3d(750.0,550.0,0)], [rg.Point3d(50.0,2450.0,0), rg.Point3d(77.1,2603.9,0), rg.Point3d(155.3,2739.3,0), rg.Point3d(275.0,2839.7,0), rg.Point3d(421.9,2893.2,0), rg.Point3d(578.1,2893.2,0), rg.Point3d(725.0,2839.7,0), rg.Point3d(844.7,2739.3,0), rg.Point3d(922.9,2603.9,0), rg.Point3d(950.0,2450.0,0), rg.Point3d(950.0,550.0,0), rg.Point3d(922.9,396.1,0), rg.Point3d(844.7,260.7,0), rg.Point3d(725.0,160.3,0), rg.Point3d(578.1,106.8,0), rg.Point3d(421.9,106.8,0), rg.Point3d(275.0,160.3,0), rg.Point3d(155.3,260.7,0), rg.Point3d(77.1,396.1,0), rg.Point3d(50.0,550.0,0), rg.Point3d(50.0,2450.0,0)]],
        '1': [[rg.Point3d(50.0,2550.0,0), rg.Point3d(400.0,2900.0,0), rg.Point3d(600.0,2900.0,0), rg.Point3d(600.0,300.0,0), rg.Point3d(950.0,300.0,0), rg.Point3d(950.0,100.0,0), rg.Point3d(50.0,100.0,0), rg.Point3d(50.0,300.0,0), rg.Point3d(400.0,300.0,0), rg.Point3d(400.0,2617.2,0), rg.Point3d(191.4,2408.6,0), rg.Point3d(50.0,2550.0,0)]],
        '2': [[rg.Point3d(950.0,2452.7,0), rg.Point3d(950.0,1939.3,0), rg.Point3d(934.7,1798.3,0), rg.Point3d(891.5,1663.3,0), rg.Point3d(822.4,1539.5,0), rg.Point3d(729.9,1431.9,0), rg.Point3d(406.1,1128.8,0), rg.Point3d(340.7,1052.4,0), rg.Point3d(291.7,964.6,0), rg.Point3d(261.1,868.9,0), rg.Point3d(250.0,769.0,0), rg.Point3d(250.0,300.0,0), rg.Point3d(950.0,300.0,0), rg.Point3d(950.0,100.0,0), rg.Point3d(502.7,100.0,0), rg.Point3d(50.0,100.0,0), rg.Point3d(50.0,768.1,0), rg.Point3d(65.3,909.1,0), rg.Point3d(108.5,1044.1,0), rg.Point3d(177.6,1167.9,0), rg.Point3d(270.1,1275.5,0), rg.Point3d(593.9,1578.6,0), rg.Point3d(659.3,1655.0,0), rg.Point3d(708.3,1742.8,0), rg.Point3d(738.9,1838.5,0), rg.Point3d(750.0,1938.4,0), rg.Point3d(750.0,2450.0,0), rg.Point3d(734.9,2535.5,0), rg.Point3d(691.5,2610.7,0), rg.Point3d(625.0,2666.5,0), rg.Point3d(543.4,2696.2,0), rg.Point3d(456.6,2696.2,0), rg.Point3d(375.0,2666.5,0), rg.Point3d(308.5,2610.7,0), rg.Point3d(265.1,2535.5,0), rg.Point3d(250.0,2450.0,0), rg.Point3d(250.0,2160.2,0), rg.Point3d(50.0,2160.2,0), rg.Point3d(50.0,2452.7,0), rg.Point3d(77.9,2605.9,0), rg.Point3d(156.2,2740.4,0), rg.Point3d(275.8,2840.2,0), rg.Point3d(422.2,2893.2,0), rg.Point3d(577.8,2893.2,0), rg.Point3d(724.2,2840.2,0), rg.Point3d(843.8,2740.4,0), rg.Point3d(922.1,2605.9,0), rg.Point3d(950.0,2452.7,0)]],
        '3': [[rg.Point3d(501.5,1367.0,0), rg.Point3d(500.0,1367.0,0), rg.Point3d(390.7,1367.0,0), rg.Point3d(390.7,1567.0,0), rg.Point3d(500.0,1567.0,0), rg.Point3d(595.3,1585.9,0), rg.Point3d(676.2,1639.7,0), rg.Point3d(730.5,1720.3,0), rg.Point3d(750.0,1815.5,0), rg.Point3d(750.0,2450.0,0), rg.Point3d(734.9,2535.5,0), rg.Point3d(691.5,2610.7,0), rg.Point3d(625.0,2666.5,0), rg.Point3d(543.4,2696.2,0), rg.Point3d(456.6,2696.2,0), rg.Point3d(375.0,2666.5,0), rg.Point3d(308.5,2610.7,0), rg.Point3d(265.1,2535.5,0), rg.Point3d(250.0,2450.0,0), rg.Point3d(250.0,2332.4,0), rg.Point3d(50.0,2332.4,0), rg.Point3d(50.0,2450.0,0), rg.Point3d(77.1,2603.9,0), rg.Point3d(155.3,2739.3,0), rg.Point3d(275.0,2839.7,0), rg.Point3d(421.9,2893.2,0), rg.Point3d(578.1,2893.2,0), rg.Point3d(725.0,2839.7,0), rg.Point3d(844.7,2739.3,0), rg.Point3d(922.9,2603.9,0), rg.Point3d(950.0,2450.0,0), rg.Point3d(950.0,1814.3,0), rg.Point3d(938.4,1715.6,0), rg.Point3d(905.5,1621.9,0), rg.Point3d(852.8,1537.6,0), rg.Point3d(782.8,1467.0,0), rg.Point3d(852.8,1396.4,0), rg.Point3d(905.5,1312.2,0), rg.Point3d(938.4,1218.4,0), rg.Point3d(950.0,1119.7,0), rg.Point3d(950.0,550.0,0), rg.Point3d(922.9,396.1,0), rg.Point3d(844.7,260.7,0), rg.Point3d(725.0,160.3,0), rg.Point3d(578.1,106.8,0), rg.Point3d(421.9,106.8,0), rg.Point3d(275.0,160.3,0), rg.Point3d(155.3,260.7,0), rg.Point3d(77.1,396.1,0), rg.Point3d(50.0,550.0,0), rg.Point3d(50.0,674.0,0), rg.Point3d(250.0,674.0,0), rg.Point3d(250.0,550.0,0), rg.Point3d(265.1,464.5,0), rg.Point3d(308.5,389.3,0), rg.Point3d(375.0,333.5,0), rg.Point3d(456.6,303.8,0), rg.Point3d(543.4,303.8,0), rg.Point3d(625.0,333.5,0), rg.Point3d(691.5,389.3,0), rg.Point3d(734.9,464.5,0), rg.Point3d(750.0,550.0,0), rg.Point3d(750.0,1118.5,0), rg.Point3d(730.7,1213.4,0), rg.Point3d(676.8,1293.8,0), rg.Point3d(596.4,1347.7,0), rg.Point3d(501.5,1367.0,0)]],
        '4': [[rg.Point3d(600.0,873.3,0), rg.Point3d(50.0,873.3,0), rg.Point3d(50.0,1500.0,0), rg.Point3d(570.2,2900.0,0), rg.Point3d(757.7,2830.3,0), rg.Point3d(250.0,1464.0,0), rg.Point3d(250.0,1073.3,0), rg.Point3d(600.0,1073.3,0), rg.Point3d(600.0,1679.2,0), rg.Point3d(800.0,1679.2,0), rg.Point3d(800.0,1073.3,0), rg.Point3d(950.0,1073.3,0), rg.Point3d(950.0,873.3,0), rg.Point3d(800.0,873.3,0), rg.Point3d(800.0,100.0,0), rg.Point3d(600.0,100.0,0), rg.Point3d(600.0,873.3,0)]],
        '5': [[rg.Point3d(750.0,1294.5,0), rg.Point3d(734.5,1379.6,0), rg.Point3d(691.0,1454.4,0), rg.Point3d(624.6,1509.8,0), rg.Point3d(543.2,1539.2,0), rg.Point3d(456.8,1539.2,0), rg.Point3d(375.4,1509.8,0), rg.Point3d(309.0,1454.4,0), rg.Point3d(265.5,1379.6,0), rg.Point3d(250.0,1294.5,0), rg.Point3d(250.0,1293.0,0), rg.Point3d(50.0,1293.0,0), rg.Point3d(50.0,2900.0,0), rg.Point3d(950.0,2900.0,0), rg.Point3d(950.0,2700.0,0), rg.Point3d(250.0,2700.0,0), rg.Point3d(250.0,1667.2,0), rg.Point3d(345.8,1715.8,0), rg.Point3d(450.4,1740.3,0), rg.Point3d(557.9,1739.3,0), rg.Point3d(662.0,1712.9,0), rg.Point3d(756.9,1662.5,0), rg.Point3d(837.1,1591.1,0), rg.Point3d(898.2,1502.7,0), rg.Point3d(936.5,1402.3,0), rg.Point3d(950.0,1295.7,0), rg.Point3d(950.0,547.3,0), rg.Point3d(922.1,394.1,0), rg.Point3d(843.8,259.6,0), rg.Point3d(724.2,159.8,0), rg.Point3d(577.8,106.8,0), rg.Point3d(422.2,106.8,0), rg.Point3d(275.8,159.8,0), rg.Point3d(156.2,259.6,0), rg.Point3d(77.9,394.1,0), rg.Point3d(50.0,547.3,0), rg.Point3d(50.0,674.0,0), rg.Point3d(250.0,674.0,0), rg.Point3d(250.0,550.0,0), rg.Point3d(265.1,464.5,0), rg.Point3d(308.5,389.3,0), rg.Point3d(375.0,333.5,0), rg.Point3d(456.6,303.8,0), rg.Point3d(543.4,303.8,0), rg.Point3d(625.0,333.5,0), rg.Point3d(691.5,389.3,0), rg.Point3d(734.9,464.5,0), rg.Point3d(750.0,550.0,0), rg.Point3d(750.0,1294.5,0)]],
        '6': [[rg.Point3d(950.0,1293.0,0), rg.Point3d(950.0,550.0,0), rg.Point3d(922.9,396.1,0), rg.Point3d(844.7,260.7,0), rg.Point3d(725.0,160.3,0), rg.Point3d(578.1,106.8,0), rg.Point3d(421.9,106.8,0), rg.Point3d(275.0,160.3,0), rg.Point3d(155.3,260.7,0), rg.Point3d(77.1,396.1,0), rg.Point3d(50.0,550.0,0), rg.Point3d(50.0,1293.0,0), rg.Point3d(50.0,1295.7,0), rg.Point3d(50.0,2450.0,0), rg.Point3d(77.1,2603.9,0), rg.Point3d(155.3,2739.3,0), rg.Point3d(275.0,2839.7,0), rg.Point3d(421.9,2893.2,0), rg.Point3d(578.1,2893.2,0), rg.Point3d(725.0,2839.7,0), rg.Point3d(844.7,2739.3,0), rg.Point3d(922.9,2603.9,0), rg.Point3d(950.0,2450.0,0), rg.Point3d(950.0,2303.8,0), rg.Point3d(750.0,2303.8,0), rg.Point3d(750.0,2450.0,0), rg.Point3d(734.9,2535.5,0), rg.Point3d(691.5,2610.7,0), rg.Point3d(625.0,2666.5,0), rg.Point3d(543.4,2696.2,0), rg.Point3d(456.6,2696.2,0), rg.Point3d(375.0,2666.5,0), rg.Point3d(308.5,2610.7,0), rg.Point3d(265.1,2535.5,0), rg.Point3d(250.0,2450.0,0), rg.Point3d(250.0,1667.2,0), rg.Point3d(346.1,1715.9,0), rg.Point3d(451.0,1740.3,0), rg.Point3d(558.7,1739.2,0), rg.Point3d(663.1,1712.4,0), rg.Point3d(758.1,1661.6,0), rg.Point3d(838.3,1589.7,0), rg.Point3d(899.2,1500.8,0), rg.Point3d(937.1,1400.0,0), rg.Point3d(950.0,1293.0,0)], [rg.Point3d(750.0,1294.5,0), rg.Point3d(734.5,1379.6,0), rg.Point3d(691.0,1454.4,0), rg.Point3d(624.6,1509.8,0), rg.Point3d(543.2,1539.2,0), rg.Point3d(456.8,1539.2,0), rg.Point3d(375.4,1509.8,0), rg.Point3d(309.0,1454.4,0), rg.Point3d(265.5,1379.6,0), rg.Point3d(250.0,1294.5,0), rg.Point3d(250.0,550.0,0), rg.Point3d(265.1,464.5,0), rg.Point3d(308.5,389.3,0), rg.Point3d(375.0,333.5,0), rg.Point3d(456.6,303.8,0), rg.Point3d(543.4,303.8,0), rg.Point3d(625.0,333.5,0), rg.Point3d(691.5,389.3,0), rg.Point3d(734.9,464.5,0), rg.Point3d(750.0,550.0,0), rg.Point3d(750.0,1294.5,0)]],
        '7': [[rg.Point3d(50.0,2900.0,0), rg.Point3d(950.0,2900.0,0), rg.Point3d(950.0,1905.7,0), rg.Point3d(600.0,1172.3,0), rg.Point3d(600.0,100.0,0), rg.Point3d(400.0,100.0,0), rg.Point3d(400.0,1217.6,0), rg.Point3d(750.0,1951.0,0), rg.Point3d(750.0,2700.0,0), rg.Point3d(250.0,2700.0,0), rg.Point3d(250.0,2034.7,0), rg.Point3d(50.0,2034.7,0), rg.Point3d(50.0,2900.0,0)]],
        '8': [[rg.Point3d(250.0,1109.2,0), rg.Point3d(250.0,550.0,0), rg.Point3d(265.1,464.5,0), rg.Point3d(308.5,389.3,0), rg.Point3d(375.0,333.5,0), rg.Point3d(456.6,303.8,0), rg.Point3d(543.4,303.8,0), rg.Point3d(625.0,333.5,0), rg.Point3d(691.5,389.3,0), rg.Point3d(734.9,464.5,0), rg.Point3d(750.0,550.0,0), rg.Point3d(750.0,1109.2,0), rg.Point3d(734.5,1194.3,0), rg.Point3d(691.0,1269.1,0), rg.Point3d(624.6,1324.5,0), rg.Point3d(543.2,1354.0,0), rg.Point3d(456.8,1354.0,0), rg.Point3d(375.4,1324.5,0), rg.Point3d(309.0,1269.1,0), rg.Point3d(265.5,1194.3,0), rg.Point3d(250.0,1109.2,0)], [rg.Point3d(750.0,1879.6,0), rg.Point3d(750.0,2450.0,0), rg.Point3d(734.9,2535.5,0), rg.Point3d(691.5,2610.7,0), rg.Point3d(625.0,2666.5,0), rg.Point3d(543.4,2696.2,0), rg.Point3d(456.6,2696.2,0), rg.Point3d(375.0,2666.5,0), rg.Point3d(308.5,2610.7,0), rg.Point3d(265.1,2535.5,0), rg.Point3d(250.0,2450.0,0), rg.Point3d(250.0,1879.6,0), rg.Point3d(265.5,1794.5,0), rg.Point3d(309.0,1719.8,0), rg.Point3d(375.4,1664.4,0), rg.Point3d(456.8,1634.9,0), rg.Point3d(543.2,1634.9,0), rg.Point3d(624.6,1664.4,0), rg.Point3d(691.0,1719.8,0), rg.Point3d(734.5,1794.5,0), rg.Point3d(750.0,1879.6,0)], [rg.Point3d(269.9,1494.4,0), rg.Point3d(179.1,1565.6,0), rg.Point3d(109.5,1657.5,0), rg.Point3d(65.5,1764.1,0), rg.Point3d(50.0,1878.4,0), rg.Point3d(50.0,2450.0,0), rg.Point3d(77.1,2603.9,0), rg.Point3d(155.3,2739.3,0), rg.Point3d(275.0,2839.7,0), rg.Point3d(421.9,2893.2,0), rg.Point3d(578.1,2893.2,0), rg.Point3d(725.0,2839.7,0), rg.Point3d(844.7,2739.3,0), rg.Point3d(922.9,2603.9,0), rg.Point3d(950.0,2450.0,0), rg.Point3d(950.0,1878.4,0), rg.Point3d(934.5,1764.1,0), rg.Point3d(890.5,1657.5,0), rg.Point3d(820.9,1565.6,0), rg.Point3d(730.1,1494.4,0), rg.Point3d(820.9,1423.2,0), rg.Point3d(890.5,1331.3,0), rg.Point3d(934.5,1224.7,0), rg.Point3d(950.0,1110.4,0), rg.Point3d(950.0,550.0,0), rg.Point3d(922.9,396.1,0), rg.Point3d(844.7,260.7,0), rg.Point3d(725.0,160.3,0), rg.Point3d(578.1,106.8,0), rg.Point3d(421.9,106.8,0), rg.Point3d(275.0,160.3,0), rg.Point3d(155.3,260.7,0), rg.Point3d(77.1,396.1,0), rg.Point3d(50.0,550.0,0), rg.Point3d(50.0,1110.4,0), rg.Point3d(65.5,1224.7,0), rg.Point3d(109.5,1331.3,0), rg.Point3d(179.1,1423.2,0), rg.Point3d(269.9,1494.4,0)]],
        '9': [[rg.Point3d(750.0,1706.1,0), rg.Point3d(750.0,2450.0,0), rg.Point3d(734.9,2535.5,0), rg.Point3d(691.5,2610.7,0), rg.Point3d(625.0,2666.5,0), rg.Point3d(543.4,2696.2,0), rg.Point3d(456.6,2696.2,0), rg.Point3d(375.0,2666.5,0), rg.Point3d(308.5,2610.7,0), rg.Point3d(265.1,2535.5,0), rg.Point3d(250.0,2450.0,0), rg.Point3d(250.0,1706.1,0), rg.Point3d(265.5,1621.0,0), rg.Point3d(309.0,1546.3,0), rg.Point3d(375.4,1490.9,0), rg.Point3d(456.8,1461.4,0), rg.Point3d(543.2,1461.4,0), rg.Point3d(624.6,1490.9,0), rg.Point3d(691.0,1546.3,0), rg.Point3d(734.5,1621.0,0), rg.Point3d(750.0,1706.1,0)], [rg.Point3d(750.0,1333.5,0), rg.Point3d(654.2,1284.9,0), rg.Point3d(549.6,1260.4,0), rg.Point3d(442.1,1261.4,0), rg.Point3d(338.0,1287.8,0), rg.Point3d(243.1,1338.2,0), rg.Point3d(162.9,1409.6,0), rg.Point3d(101.8,1498.0,0), rg.Point3d(63.5,1598.4,0), rg.Point3d(50.0,1705.0,0), rg.Point3d(50.0,2452.7,0), rg.Point3d(77.9,2605.9,0), rg.Point3d(156.2,2740.4,0), rg.Point3d(275.8,2840.2,0), rg.Point3d(422.2,2893.2,0), rg.Point3d(577.8,2893.2,0), rg.Point3d(724.2,2840.2,0), rg.Point3d(843.8,2740.4,0), rg.Point3d(922.1,2605.9,0), rg.Point3d(950.0,2452.7,0), rg.Point3d(950.0,547.3,0), rg.Point3d(922.1,394.1,0), rg.Point3d(843.8,259.6,0), rg.Point3d(724.2,159.8,0), rg.Point3d(577.8,106.8,0), rg.Point3d(422.2,106.8,0), rg.Point3d(275.8,159.8,0), rg.Point3d(156.2,259.6,0), rg.Point3d(77.9,394.1,0), rg.Point3d(50.0,547.3,0), rg.Point3d(50.0,674.0,0), rg.Point3d(250.0,674.0,0), rg.Point3d(250.0,550.0,0), rg.Point3d(265.1,464.5,0), rg.Point3d(308.5,389.3,0), rg.Point3d(375.0,333.5,0), rg.Point3d(456.6,303.8,0), rg.Point3d(543.4,303.8,0), rg.Point3d(625.0,333.5,0), rg.Point3d(691.5,389.3,0), rg.Point3d(734.9,464.5,0), rg.Point3d(750.0,550.0,0), rg.Point3d(750.0,1333.5,0)]],
    }
    SYMBOL_DB = {
        '횡단보도': [[rg.Point3d(-0.0,-1724.4,0), rg.Point3d(512.1,0.0,0), rg.Point3d(-0.0,1724.4,0), rg.Point3d(-512.1,0.0,0), rg.Point3d(-0.0,-1724.4,0)], [rg.Point3d(-0.0,-2525.3,0), rg.Point3d(750.0,0.0,0), rg.Point3d(-0.0,2525.2,0), rg.Point3d(-750.0,0.0,0), rg.Point3d(-0.0,-2525.3,0)]],
        '양보': [[rg.Point3d(501.0,1503.0,0), rg.Point3d(-501.0,1503.0,0), rg.Point3d(-0.0,-1503.0,0), rg.Point3d(501.0,1503.0,0)], [rg.Point3d(-0.0,-588.8,0), rg.Point3d(-298.5,1202.4,0), rg.Point3d(298.5,1202.4,0), rg.Point3d(-0.0,-588.8,0)]],
    }
    ARROW_MASTER_DB = {
        'S': [[rg.Point3d(0.0,2500.0,0), rg.Point3d(300.0,300.0,0), rg.Point3d(75.0,300.0,0), rg.Point3d(75.0,-2500.0,0), rg.Point3d(-75.0,-2500.0,0), rg.Point3d(-75.0,300.0,0), rg.Point3d(-300.0,300.0,0), rg.Point3d(0.0,2500.0,0)]],
        'SX': [[rg.Point3d(-75.0,-620.1,0), rg.Point3d(75.0,-620.1,0), rg.Point3d(75.0,300.0,0), rg.Point3d(300.0,300.0,0), rg.Point3d(0.0,2500.0,0), rg.Point3d(-300.0,300.0,0), rg.Point3d(-75.0,300.0,0), rg.Point3d(-75.0,-620.1,0)], [rg.Point3d(86.6,-1100.0,0), rg.Point3d(565.0,-271.5,0), rg.Point3d(435.0,-196.5,0), rg.Point3d(0.0,-950.0,0), rg.Point3d(-435.0,-196.5,0), rg.Point3d(-565.0,-271.5,0), rg.Point3d(-86.6,-1100.0,0), rg.Point3d(-565.0,-1928.5,0), rg.Point3d(-435.0,-2003.5,0), rg.Point3d(0.0,-1250.0,0), rg.Point3d(435.0,-2003.5,0), rg.Point3d(565.0,-1928.5,0), rg.Point3d(86.6,-1100.0,0)], [rg.Point3d(75.0,-1579.9,0), rg.Point3d(-75.0,-1579.9,0), rg.Point3d(-75.0,-2500.0,0), rg.Point3d(75.0,-2500.0,0), rg.Point3d(75.0,-1579.9,0)]],
        'L': [[rg.Point3d(-525.0,1700.0,0), rg.Point3d(-420.8,1690.9,0), rg.Point3d(-319.8,1663.8,0), rg.Point3d(-225.0,1619.6,0), rg.Point3d(-139.3,1559.6,0), rg.Point3d(-65.4,1485.7,0), rg.Point3d(-5.4,1400.0,0), rg.Point3d(38.8,1305.2,0), rg.Point3d(65.9,1204.2,0), rg.Point3d(75.0,1100.0,0), rg.Point3d(75.0,-2500.0,0), rg.Point3d(-75.0,-2500.0,0), rg.Point3d(-75.0,600.0,0), rg.Point3d(-81.7,681.3,0), rg.Point3d(-101.5,760.5,0), rg.Point3d(-133.9,835.4,0), rg.Point3d(-178.1,904.0,0), rg.Point3d(-232.8,964.6,0), rg.Point3d(-296.7,1015.4,0), rg.Point3d(-367.9,1055.1,0), rg.Point3d(-444.7,1082.7,0), rg.Point3d(-525.0,1097.5,0), rg.Point3d(-525.0,300.0,0), rg.Point3d(-1125.0,1400.0,0), rg.Point3d(-525.0,2500.0,0), rg.Point3d(-525.0,1700.0,0)]],
        'LX': [[rg.Point3d(-75.0,600.0,0), rg.Point3d(-81.7,681.3,0), rg.Point3d(-101.5,760.5,0), rg.Point3d(-133.9,835.4,0), rg.Point3d(-178.1,904.0,0), rg.Point3d(-232.8,964.6,0), rg.Point3d(-296.7,1015.4,0), rg.Point3d(-367.9,1055.1,0), rg.Point3d(-444.7,1082.7,0), rg.Point3d(-525.0,1097.5,0), rg.Point3d(-525.0,300.0,0), rg.Point3d(-1125.0,1400.0,0), rg.Point3d(-525.0,2500.0,0), rg.Point3d(-525.0,1700.0,0), rg.Point3d(-420.8,1690.9,0), rg.Point3d(-319.8,1663.8,0), rg.Point3d(-225.0,1619.6,0), rg.Point3d(-139.3,1559.6,0), rg.Point3d(-65.4,1485.7,0), rg.Point3d(-5.4,1400.0,0), rg.Point3d(38.8,1305.2,0), rg.Point3d(65.9,1204.2,0), rg.Point3d(75.0,1100.0,0), rg.Point3d(75.0,-620.1,0), rg.Point3d(-75.0,-620.1,0), rg.Point3d(-75.0,600.0,0)], [rg.Point3d(86.6,-1100.0,0), rg.Point3d(565.0,-271.5,0), rg.Point3d(435.0,-196.5,0), rg.Point3d(0.0,-950.0,0), rg.Point3d(-435.0,-196.5,0), rg.Point3d(-565.0,-271.5,0), rg.Point3d(-86.6,-1100.0,0), rg.Point3d(-565.0,-1928.5,0), rg.Point3d(-435.0,-2003.5,0), rg.Point3d(0.0,-1250.0,0), rg.Point3d(435.0,-2003.5,0), rg.Point3d(565.0,-1928.5,0), rg.Point3d(86.6,-1100.0,0)], [rg.Point3d(75.0,-1579.9,0), rg.Point3d(75.0,-2500.0,0), rg.Point3d(-75.0,-2500.0,0), rg.Point3d(-75.0,-1579.9,0), rg.Point3d(75.0,-1579.9,0)]],
        'SL': [[rg.Point3d(300.0,300.0,0), rg.Point3d(75.0,300.0,0), rg.Point3d(75.0,-2500.0,0), rg.Point3d(-75.0,-2500.0,0), rg.Point3d(-75.0,-1542.9,0), rg.Point3d(-375.0,-1402.5,0), rg.Point3d(-375.0,-2200.0,0), rg.Point3d(-975.0,-1100.0,0), rg.Point3d(-375.0,-0.0,0), rg.Point3d(-375.0,-883.5,0), rg.Point3d(-75.0,-1085.9,0), rg.Point3d(-75.0,300.0,0), rg.Point3d(-300.0,300.0,0), rg.Point3d(0.0,2500.0,0), rg.Point3d(300.0,300.0,0)]],
        'SLX': [[rg.Point3d(-75.0,-2158.5,0), rg.Point3d(-75.0,-4084.9,0), rg.Point3d(75.0,-4084.9,0), rg.Point3d(75.0,-2158.5,0), rg.Point3d(-75.0,-2158.5,0)], [rg.Point3d(86.6,-1678.6,0), rg.Point3d(565.0,-850.0,0), rg.Point3d(435.0,-775.0,0), rg.Point3d(0.0,-1528.6,0), rg.Point3d(-435.0,-775.0,0), rg.Point3d(-565.0,-850.0,0), rg.Point3d(-86.6,-1678.6,0), rg.Point3d(-565.0,-2507.1,0), rg.Point3d(-435.0,-2582.1,0), rg.Point3d(0.0,-1828.6,0), rg.Point3d(435.0,-2582.1,0), rg.Point3d(565.0,-2507.1,0), rg.Point3d(86.6,-1678.6,0)], [rg.Point3d(75.0,-1198.6,0), rg.Point3d(75.0,1884.9,0), rg.Point3d(300.0,1884.9,0), rg.Point3d(0.0,4084.9,0), rg.Point3d(-300.0,1884.9,0), rg.Point3d(-75.0,1884.9,0), rg.Point3d(-75.0,499.0,0), rg.Point3d(-375.0,701.4,0), rg.Point3d(-375.0,1584.9,0), rg.Point3d(-975.0,484.9,0), rg.Point3d(-375.0,-615.1,0), rg.Point3d(-375.0,182.4,0), rg.Point3d(-75.0,41.9,0), rg.Point3d(-75.0,-1198.6,0), rg.Point3d(75.0,-1198.6,0)]],
        'LU': [[rg.Point3d(-100.0,335.7,0), rg.Point3d(-87.5,335.6,0), rg.Point3d(-75.0,335.1,0), rg.Point3d(-75.0,600.0,0), rg.Point3d(-81.7,681.3,0), rg.Point3d(-101.5,760.5,0), rg.Point3d(-133.9,835.4,0), rg.Point3d(-178.1,904.0,0), rg.Point3d(-232.8,964.6,0), rg.Point3d(-296.7,1015.4,0), rg.Point3d(-367.9,1055.1,0), rg.Point3d(-444.7,1082.7,0), rg.Point3d(-525.0,1097.5,0), rg.Point3d(-525.0,300.0,0), rg.Point3d(-1125.0,1400.0,0), rg.Point3d(-525.0,2500.0,0), rg.Point3d(-525.0,1616.5,0), rg.Point3d(-410.6,1557.5,0), rg.Point3d(-304.7,1484.4,0), rg.Point3d(-209.1,1398.2,0), rg.Point3d(-125.3,1300.4,0), rg.Point3d(-54.8,1192.7,0), rg.Point3d(1.3,1076.9,0), rg.Point3d(42.0,954.8,0), rg.Point3d(66.7,828.5,0), rg.Point3d(75.0,700.0,0), rg.Point3d(75.0,-2500.0,0), rg.Point3d(-75.0,-2500.0,0), rg.Point3d(-75.0,47.0,0), rg.Point3d(-87.5,47.6,0), rg.Point3d(-100.0,47.9,0), rg.Point3d(-175.0,47.9,0), rg.Point3d(-235.5,42.6,0), rg.Point3d(-294.3,26.9,0), rg.Point3d(-349.4,1.3,0), rg.Point3d(-399.2,-33.4,0), rg.Point3d(-442.3,-76.3,0), rg.Point3d(-477.4,-125.9,0), rg.Point3d(-503.3,-180.9,0), rg.Point3d(-519.3,-239.5,0), rg.Point3d(-525.0,-300.0,0), rg.Point3d(-300.0,-300.0,0), rg.Point3d(-600.0,-2500.0,0), rg.Point3d(-900.0,-300.0,0), rg.Point3d(-656.2,-300.0,0), rg.Point3d(-673.8,-199.2,0), rg.Point3d(-670.4,-96.9,0), rg.Point3d(-646.3,2.6,0), rg.Point3d(-602.5,95.1,0), rg.Point3d(-540.7,176.7,0), rg.Point3d(-463.6,244.0,0), rg.Point3d(-374.4,294.3,0), rg.Point3d(-276.8,325.2,0), rg.Point3d(-175.0,335.7,0), rg.Point3d(-100.0,335.7,0)]],
        'LUX': [[rg.Point3d(86.6,-1536.8,0), rg.Point3d(565.0,-708.3,0), rg.Point3d(435.0,-633.3,0), rg.Point3d(0.0,-1386.8,0), rg.Point3d(-435.0,-633.3,0), rg.Point3d(-565.0,-708.3,0), rg.Point3d(-86.6,-1536.8,0), rg.Point3d(-565.0,-2365.3,0), rg.Point3d(-435.0,-2440.3,0), rg.Point3d(0.0,-1686.8,0), rg.Point3d(435.0,-2440.3,0), rg.Point3d(565.0,-2365.3,0), rg.Point3d(86.6,-1536.8,0)], [rg.Point3d(-75.0,-2016.7,0), rg.Point3d(-75.0,-3943.1,0), rg.Point3d(75.0,-3943.1,0), rg.Point3d(75.0,-2016.7,0), rg.Point3d(-75.0,-2016.7,0)], [rg.Point3d(-100.0,1778.8,0), rg.Point3d(-87.5,1778.7,0), rg.Point3d(-75.0,1778.2,0), rg.Point3d(-75.0,2043.1,0), rg.Point3d(-81.7,2124.4,0), rg.Point3d(-101.5,2203.6,0), rg.Point3d(-133.9,2278.5,0), rg.Point3d(-178.1,2347.1,0), rg.Point3d(-232.8,2407.7,0), rg.Point3d(-296.7,2458.5,0), rg.Point3d(-367.9,2498.2,0), rg.Point3d(-444.7,2525.8,0), rg.Point3d(-525.0,2540.6,0), rg.Point3d(-525.0,1743.1,0), rg.Point3d(-1125.0,2843.1,0), rg.Point3d(-525.0,3943.1,0), rg.Point3d(-525.0,3059.6,0), rg.Point3d(-410.6,3000.6,0), rg.Point3d(-304.7,2927.5,0), rg.Point3d(-209.1,2841.3,0), rg.Point3d(-125.3,2743.5,0), rg.Point3d(-54.8,2635.8,0), rg.Point3d(1.3,2520.0,0), rg.Point3d(42.0,2397.9,0), rg.Point3d(66.7,2271.6,0), rg.Point3d(75.0,2143.1,0), rg.Point3d(75.0,-1056.9,0), rg.Point3d(-75.0,-1056.9,0), rg.Point3d(-75.0,1490.1,0), rg.Point3d(-87.5,1490.7,0), rg.Point3d(-100.0,1491.0,0), rg.Point3d(-175.0,1491.0,0), rg.Point3d(-235.5,1485.7,0), rg.Point3d(-294.3,1470.0,0), rg.Point3d(-349.4,1444.4,0), rg.Point3d(-399.2,1409.7,0), rg.Point3d(-442.3,1366.8,0), rg.Point3d(-477.4,1317.2,0), rg.Point3d(-503.3,1262.2,0), rg.Point3d(-519.3,1203.6,0), rg.Point3d(-525.0,1143.1,0), rg.Point3d(-300.0,1143.1,0), rg.Point3d(-600.0,-1056.9,0), rg.Point3d(-900.0,1143.1,0), rg.Point3d(-656.2,1143.1,0), rg.Point3d(-673.8,1243.9,0), rg.Point3d(-670.4,1346.3,0), rg.Point3d(-646.3,1445.7,0), rg.Point3d(-602.5,1538.2,0), rg.Point3d(-540.7,1619.8,0), rg.Point3d(-463.6,1687.1,0), rg.Point3d(-374.4,1737.4,0), rg.Point3d(-276.8,1768.3,0), rg.Point3d(-175.0,1778.8,0), rg.Point3d(-100.0,1778.8,0)]],
        'U': [[rg.Point3d(-350.0,1750.0,0), rg.Point3d(-350.0,1350.0,0), rg.Point3d(-125.0,1350.0,0), rg.Point3d(-425.0,-850.0,0), rg.Point3d(-725.0,1350.0,0), rg.Point3d(-500.0,1350.0,0), rg.Point3d(-500.0,2250.0,0), rg.Point3d(-469.8,2421.0,0), rg.Point3d(-383.0,2571.4,0), rg.Point3d(-250.0,2683.0,0), rg.Point3d(-86.8,2742.4,0), rg.Point3d(86.8,2742.4,0), rg.Point3d(250.0,2683.0,0), rg.Point3d(383.0,2571.4,0), rg.Point3d(469.8,2421.0,0), rg.Point3d(500.0,2250.0,0), rg.Point3d(500.0,-2250.0,0), rg.Point3d(350.0,-2250.0,0), rg.Point3d(350.0,1750.0,0), rg.Point3d(328.9,1869.7,0), rg.Point3d(268.1,1975.0,0), rg.Point3d(175.0,2053.1,0), rg.Point3d(60.8,2094.7,0), rg.Point3d(-60.8,2094.7,0), rg.Point3d(-175.0,2053.1,0), rg.Point3d(-268.1,1975.0,0), rg.Point3d(-328.9,1869.7,0), rg.Point3d(-350.0,1750.0,0)]],
        'UX': [[rg.Point3d(350.0,1500.0,0), rg.Point3d(350.0,-620.1,0), rg.Point3d(500.0,-620.1,0), rg.Point3d(500.0,2000.0,0), rg.Point3d(469.8,2171.0,0), rg.Point3d(383.0,2321.4,0), rg.Point3d(250.0,2433.0,0), rg.Point3d(86.8,2492.4,0), rg.Point3d(-86.8,2492.4,0), rg.Point3d(-250.0,2433.0,0), rg.Point3d(-383.0,2321.4,0), rg.Point3d(-469.8,2171.0,0), rg.Point3d(-500.0,2000.0,0), rg.Point3d(-500.0,1100.0,0), rg.Point3d(-725.0,1100.0,0), rg.Point3d(-425.0,-1100.0,0), rg.Point3d(-125.0,1100.0,0), rg.Point3d(-350.0,1100.0,0), rg.Point3d(-350.0,1500.0,0), rg.Point3d(-328.9,1619.7,0), rg.Point3d(-268.1,1725.0,0), rg.Point3d(-175.0,1803.1,0), rg.Point3d(-60.8,1844.7,0), rg.Point3d(60.8,1844.7,0), rg.Point3d(175.0,1803.1,0), rg.Point3d(268.1,1725.0,0), rg.Point3d(328.9,1619.7,0), rg.Point3d(350.0,1500.0,0)], [rg.Point3d(511.6,-1100.0,0), rg.Point3d(990.0,-271.5,0), rg.Point3d(860.0,-196.5,0), rg.Point3d(425.0,-950.0,0), rg.Point3d(-10.0,-196.5,0), rg.Point3d(-140.0,-271.5,0), rg.Point3d(338.4,-1100.0,0), rg.Point3d(-140.0,-1928.5,0), rg.Point3d(-10.0,-2003.5,0), rg.Point3d(425.0,-1250.0,0), rg.Point3d(860.0,-2003.5,0), rg.Point3d(990.0,-1928.5,0), rg.Point3d(511.6,-1100.0,0)], [rg.Point3d(500.0,-1579.9,0), rg.Point3d(350.0,-1579.9,0), rg.Point3d(350.0,-2500.0,0), rg.Point3d(500.0,-2500.0,0), rg.Point3d(500.0,-1579.9,0)]],
        'LR': [[rg.Point3d(-525.0,1616.5,0), rg.Point3d(-525.0,2500.0,0), rg.Point3d(-1125.0,1400.0,0), rg.Point3d(-525.0,300.0,0), rg.Point3d(-525.0,1097.5,0), rg.Point3d(-349.5,1046.3,0), rg.Point3d(-204.2,935.4,0), rg.Point3d(-108.4,779.7,0), rg.Point3d(-75.0,600.0,0), rg.Point3d(-75.0,-2500.0,0), rg.Point3d(75.0,-2500.0,0), rg.Point3d(75.0,600.0,0), rg.Point3d(108.4,779.7,0), rg.Point3d(204.2,935.4,0), rg.Point3d(349.5,1046.3,0), rg.Point3d(525.0,1097.5,0), rg.Point3d(525.0,300.0,0), rg.Point3d(1125.0,1400.0,0), rg.Point3d(525.0,2500.0,0), rg.Point3d(525.0,1616.5,0), rg.Point3d(357.1,1523.1,0), rg.Point3d(210.2,1399.4,0), rg.Point3d(89.7,1249.8,0), rg.Point3d(0.0,1080.0,0), rg.Point3d(-89.7,1249.8,0), rg.Point3d(-210.2,1399.4,0), rg.Point3d(-357.1,1523.1,0), rg.Point3d(-525.0,1616.5,0)]],
        'LRX': [[rg.Point3d(0.0,1080.0,0), rg.Point3d(-89.7,1249.8,0), rg.Point3d(-210.2,1399.4,0), rg.Point3d(-357.1,1523.1,0), rg.Point3d(-525.0,1616.5,0), rg.Point3d(-525.0,2500.0,0), rg.Point3d(-1125.0,1400.0,0), rg.Point3d(-525.0,300.0,0), rg.Point3d(-525.0,1097.5,0), rg.Point3d(-349.5,1046.3,0), rg.Point3d(-204.2,935.4,0), rg.Point3d(-108.4,779.7,0), rg.Point3d(-75.0,600.0,0), rg.Point3d(-75.0,-620.1,0), rg.Point3d(75.0,-620.1,0), rg.Point3d(75.0,600.0,0), rg.Point3d(108.4,779.7,0), rg.Point3d(204.2,935.4,0), rg.Point3d(349.5,1046.3,0), rg.Point3d(525.0,1097.5,0), rg.Point3d(525.0,300.0,0), rg.Point3d(1125.0,1400.0,0), rg.Point3d(525.0,2500.0,0), rg.Point3d(525.0,1616.5,0), rg.Point3d(357.1,1523.1,0), rg.Point3d(210.2,1399.4,0), rg.Point3d(89.7,1249.8,0), rg.Point3d(0.0,1080.0,0)], [rg.Point3d(75.0,-1579.9,0), rg.Point3d(-75.0,-1579.9,0), rg.Point3d(-75.0,-2500.0,0), rg.Point3d(75.0,-2500.0,0), rg.Point3d(75.0,-1579.9,0)], [rg.Point3d(86.6,-1100.0,0), rg.Point3d(565.0,-271.5,0), rg.Point3d(435.0,-196.5,0), rg.Point3d(-0.0,-950.0,0), rg.Point3d(-435.0,-196.5,0), rg.Point3d(-565.0,-271.5,0), rg.Point3d(-86.6,-1100.0,0), rg.Point3d(-565.0,-1928.5,0), rg.Point3d(-435.0,-2003.5,0), rg.Point3d(-0.0,-1250.0,0), rg.Point3d(435.0,-2003.5,0), rg.Point3d(565.0,-1928.5,0), rg.Point3d(86.6,-1100.0,0)]],
        'SLR': [[rg.Point3d(300.0,300.0,0), rg.Point3d(0.0,2500.0,0), rg.Point3d(-300.0,300.0,0), rg.Point3d(-75.0,300.0,0), rg.Point3d(-75.0,-1085.9,0), rg.Point3d(-375.0,-883.5,0), rg.Point3d(-375.0,-0.0,0), rg.Point3d(-975.0,-1100.0,0), rg.Point3d(-375.0,-2200.0,0), rg.Point3d(-375.0,-1402.5,0), rg.Point3d(-75.0,-1542.9,0), rg.Point3d(-75.0,-2500.0,0), rg.Point3d(75.0,-2500.0,0), rg.Point3d(75.0,-1542.9,0), rg.Point3d(375.0,-1402.5,0), rg.Point3d(375.0,-2200.0,0), rg.Point3d(975.0,-1100.0,0), rg.Point3d(375.0,0.0,0), rg.Point3d(375.0,-883.5,0), rg.Point3d(75.0,-1085.9,0), rg.Point3d(75.0,300.0,0), rg.Point3d(300.0,300.0,0)]],
    }

    @staticmethod
    def get_arrow_master(type_key):
        should_mirror = False
        source_key = type_key
        mirror_map = {'R': 'L', 'RX': 'LX', 'SR': 'SL', 'SRX': 'SLX', 'RU': 'LU', 'RUX': 'LUX'}
        if type_key in mirror_map:
            source_key = mirror_map[type_key]
            should_mirror = True
        if source_key not in MarkGenerator.ARROW_MASTER_DB: return []
        raw_pts_list = MarkGenerator.ARROW_MASTER_DB[source_key]
        curves = []
        for pts in raw_pts_list:
            if should_mirror:
                pts = [rg.Point3d(-p.X, p.Y, p.Z) for p in pts]
            curves.append(rg.PolylineCurve(pts))
        return curves

    @staticmethod
    def get_symbol_custom(name):
        combined_curves = []
        pts_list = MarkGenerator.SYMBOL_DB.get(name, [])
        for pts in pts_list:
            combined_curves.append(rg.Polyline(pts).ToPolylineCurve())
        return combined_curves

    @staticmethod
    def get_number_arranged(input_str):
        combined_curves = []
        digits = [c for c in input_str if c in MarkGenerator.DIGIT_DB]
        if not digits: return []
        gap = 100
        total_width = (len(digits) * MarkGenerator.W) + ((len(digits)-1) * gap)
        start_x = -total_width / 2.0
        for i, char in enumerate(digits):
            pts_list = MarkGenerator.DIGIT_DB[char]
            x_offset = start_x + (i * (MarkGenerator.W + gap))
            for pts in pts_list:
                moved_pts = [rg.Point3d(p.X + x_offset, p.Y - 1500, 0) for p in pts]
                combined_curves.append(rg.Polyline(moved_pts).ToPolylineCurve())
        return combined_curves
    
    @staticmethod
    def get_circled_text(input_str):
        combined_curves = []
        if not input_str: return []

        # 1. 테두리 원 생성 (WorldXY 기준)
        # 기본 커브 (반지름 1000)
        circle_inner = rg.Circle(rg.Plane.WorldXY, 1000.0).ToNurbsCurve()
        # 바깥 커브 (반지름 1200)
        circle_outer = rg.Circle(rg.Plane.WorldXY, 1200.0).ToNurbsCurve()
        
        combined_curves.append(circle_inner)
        combined_curves.append(circle_outer)

        # 2. 텍스트 커브 추출 (Rhino API 활용)
        # CreateTextOutlines(텍스트, 폰트, 높이, 스타일(1=Bold), 닫힌커브여부, 평면, 소문자스케일, 공차)
        try:
            text_curves = rg.Curve.CreateTextOutlines(input_str, "Arial", 1000.0, 1, True, rg.Plane.WorldXY, 1.0, 0.01)
        except Exception as e:
            print("폰트 추출 에러:", e)
            return combined_curves

        if text_curves:
            # 3. 텍스트 그룹의 전체 영역(Bounding Box) 계산
            bbox = rg.BoundingBox.Empty
            for crv in text_curves:
                bbox.Union(crv.GetBoundingBox(True))
            
            # 중심을 0,0,0으로 이동하는 행렬
            center_pt = bbox.Center
            move_vec = rg.Point3d.Origin - center_pt
            xform_move = rg.Transform.Translation(move_vec)
            
            # 4. 크기 자동 조절 (반지름 1000짜리 원 안에 들어가도록)
            w = bbox.Max.X - bbox.Min.X
            h = bbox.Max.Y - bbox.Min.Y
            max_dim = max(w, h)
            
            # 안쪽 원(지름 2000) 안에서 여백(Padding)을 주기 위해 타겟 지름을 1500으로 설정
            target_dim = 1500.0 
            scale_factor = target_dim / max_dim if max_dim > 0 else 1.0
            
            xform_scale = rg.Transform.Scale(rg.Point3d.Origin, scale_factor)
            
            # 이동 후 스케일 적용
            final_xform = xform_scale * xform_move
            
            for crv in text_curves:
                crv.Transform(final_xform)
                combined_curves.append(crv)
                
        return combined_curves

# ==============================================================================
# [2. UI 레이어]
# ==============================================================================
class SimpleConduit(rd.DisplayConduit):
    def __init__(self):
        rd.DisplayConduit.__init__(self)
        self.curves = []
        self.color = System.Drawing.Color.Red
    def DrawForeground(self, e):
        for c in self.curves:
            if c and c.IsValid: e.Display.DrawCurve(c, self.color, 2)

class CategoryIconPicker(forms.Dialog[str]):
    def __init__(self):
        self.Title = "노면표시 종류 선택"
        self.Resizable = False
        self.Padding = drawing.Padding(15)
        self.btn_esc = forms.Button(Text="Cancel")
        self.btn_esc.Click += lambda s,e: self.Close(None)
        self.AbortButton = self.btn_esc
        btn_size = drawing.Size(120, 140)
        img_pos = forms.ButtonImagePosition.Above
        self.btn_arrow = forms.Button(Text="방향표시", Size=btn_size, Image=get_icon(IMG_ARROW), ImagePosition=img_pos)
        self.btn_arrow.Click += lambda s,e: self.Close("방향표시")
        self.btn_symbol = forms.Button(Text="심볼", Size=btn_size, Image=get_icon(IMG_SYMBOL), ImagePosition=img_pos)
        self.btn_symbol.Click += lambda s,e: self.Close("심볼")
        self.btn_text = forms.Button(Text="텍스트", Size=btn_size, Image=get_icon(IMG_TEXT), ImagePosition=img_pos)
        self.btn_text.Click += lambda s,e: self.Close("텍스트")
        layout = forms.DynamicLayout()
        layout.BeginHorizontal()
        layout.Add(self.btn_arrow); layout.Add(self.btn_symbol); layout.Add(self.btn_text)
        layout.EndHorizontal()
        self.Content = layout

class BaseMarkDialog(forms.Dialog[bool]):
    def __init__(self, base_plane, mode):
        self.Title = "세부 설정 - " + mode
        self.base_plane = base_plane
        
        # 💡 상태 변수 3가지로 확장 (좌우, 상하, 회전)
        self.mirror_x = False
        self.mirror_y = False
        self.rot_180 = False
        
        self.conduit = SimpleConduit()
        self.conduit.Enabled = True
        
        self.btn_back = forms.Button(Text="Back")
        self.btn_back.Click += lambda s,e: self.Close(False)
        self.AbortButton = self.btn_back
        
        # 💡 변환 버튼 3개 생성
        self.btn_mirror_x = forms.Button(Text="좌우 반전")
        self.btn_mirror_x.Click += self.OnMirrorX
        
        self.btn_mirror_y = forms.Button(Text="상하 반전")
        self.btn_mirror_y.Click += self.OnMirrorY
        
        self.btn_rot_180 = forms.Button(Text="180도 회전")
        self.btn_rot_180.Click += self.OnRot180
        
        self.btn_ok = forms.Button(Text="배치 확정")
        self.btn_ok.Click += lambda s, e: self.Close(True)
        self.DefaultButton = self.btn_ok
        
        self.layout = forms.DynamicLayout()
        self.layout.Padding = drawing.Padding(20)
        self.SetupUI()
        self.layout.AddRow(None)
        
        # 💡 변환 버튼들을 가로로 깔끔하게 배치
        transform_layout = forms.DynamicLayout()
        transform_layout.BeginHorizontal()
        transform_layout.Add(self.btn_mirror_x)
        transform_layout.Add(self.btn_mirror_y)
        transform_layout.Add(self.btn_rot_180)
        transform_layout.EndHorizontal()
        
        self.layout.AddRow(transform_layout)
        self.layout.AddRow(self.btn_ok)
        self.Content = self.layout
        self.Shown += lambda s,e: self.UpdatePreview()
        
    # 💡 버튼 클릭 이벤트 (상태 토글 및 미리보기 업데이트)
    def OnMirrorX(self, s, e):
        self.mirror_x = not self.mirror_x
        self.UpdatePreview()
        
    def OnMirrorY(self, s, e):
        self.mirror_y = not self.mirror_y
        self.UpdatePreview()
        
    def OnRot180(self, s, e):
        self.rot_180 = not self.rot_180
        self.UpdatePreview()
        
    def UpdatePreview(self):
        parts = self.GetGeometry()
        
        plane = rg.Plane(self.base_plane)
        plane.Translate(plane.ZAxis * 0.5)
        
        plane_xform = rg.Transform.PlaneToPlane(rg.Plane.WorldXY, plane)
        
        local_xform = rg.Transform.Identity
        
        if self.mirror_x:
            local_xform = rg.Transform.Scale(rg.Plane.WorldXY, -1.0, 1.0, 1.0) * local_xform
        if self.mirror_y:
            local_xform = rg.Transform.Scale(rg.Plane.WorldXY, 1.0, -1.0, 1.0) * local_xform
        if self.rot_180:
            local_xform = rg.Transform.Rotation(math.pi, rg.Vector3d.ZAxis, rg.Point3d.Origin) * local_xform
            
        final_xform = plane_xform * local_xform
        
        self.conduit.curves = []
        for p in parts:
            if p:
                c = p.DuplicateCurve()
                c.Transform(final_xform)
                self.conduit.curves.append(c)
        Rhino.RhinoDoc.ActiveDoc.Views.Redraw()
        
    def OnClosed(self, e):
        self.conduit.Enabled = False
        Rhino.RhinoDoc.ActiveDoc.Views.Redraw()

class ArrowDialog(BaseMarkDialog):
    def SetupUI(self):
        self.VALID_LIST = ["S", "SX", "L", "LX", "R", "RX", "SL", "SLX", "SR", "SRX", "LU", "LUX", "LR", "LRX", "U", "UX", "SLR"]
        self.cb_s = forms.CheckBox(Text="직진 (S)")
        self.cb_l = forms.CheckBox(Text="좌회전 (L)")
        self.cb_r = forms.CheckBox(Text="우회전 (R)")
        self.cb_u = forms.CheckBox(Text="유턴 (U)")
        self.cb_x = forms.CheckBox(Text="불가 (X)")
        self.checkboxes = [self.cb_s, self.cb_l, self.cb_r, self.cb_u, self.cb_x]
        for cb in self.checkboxes:
            cb.CheckedChanged += lambda s, e: self.UpdatePreview()
        self.layout.AddRow(forms.Label(Text="방향 구성 요소를 선택하세요:"))
        grid = forms.DynamicLayout()
        grid.Spacing = drawing.Size(10, 5)
        grid.BeginHorizontal()
        grid.Add(self.cb_s); grid.Add(self.cb_l)
        grid.EndHorizontal()
        grid.BeginHorizontal()
        grid.Add(self.cb_r); grid.Add(self.cb_u)
        grid.EndHorizontal()
        grid.BeginHorizontal()
        grid.Add(self.cb_x)
        grid.EndHorizontal()
        self.layout.AddRow(grid)
        self.lbl_status = forms.Label(Text="조합: -", TextColor=drawing.Colors.Gray)
        self.layout.AddRow(self.lbl_status)
    def GetCurrentTypeKey(self):
        codes = []
        if self.cb_s.Checked: codes.append("S")
        if self.cb_l.Checked: codes.append("L")
        if self.cb_r.Checked: codes.append("R")
        if self.cb_u.Checked: codes.append("U")
        if self.cb_x.Checked: codes.append("X")
        return "".join(codes)
    def GetGeometry(self):
        type_key = self.GetCurrentTypeKey()
        if type_key in self.VALID_LIST:
            self.lbl_status.Text = "조합: " + type_key + " (유효)"
            self.lbl_status.TextColor = drawing.Colors.DodgerBlue
            self.btn_ok.Enabled = True
            return MarkGenerator.get_arrow_master(type_key)
        else:
            self.lbl_status.Text = "조합: " + (type_key if type_key else "없음") + " (미지원)"
            self.lbl_status.TextColor = drawing.Colors.Red
            self.btn_ok.Enabled = False
            return []

class SymbolDialog(BaseMarkDialog):
    def SetupUI(self):
        self.list = forms.ListBox(); self.list.DataStore = ["양보", "횡단보도"]; self.list.SelectedIndex = 0
        self.list.SelectedIndexChanged += lambda s,e: self.UpdatePreview()
        self.layout.AddRow(forms.Label(Text="심볼 선택:"))
        self.layout.AddRow(self.list)
    def GetGeometry(self):
        return MarkGenerator.get_symbol_custom(self.list.SelectedValue)

class TextDialog(BaseMarkDialog):
    def SetupUI(self):
        self.txt = forms.TextBox()
        self.txt.PlaceholderText = "숫자 입력 (예: 80)"
        self.txt.KeyDown += self.OnTextKeyDown
        
        self.cb_border = forms.CheckBox(Text="원형 테두리 적용 (속도표시)")
        self.cb_border.CheckedChanged += lambda s, e: self.UpdatePreview()
        
        self.btn_confirm = forms.Button(Text="텍스트 확인")
        self.btn_confirm.Click += lambda s,e: self.UpdatePreview()
        
        self.layout.AddRow(forms.Label(Text="표시할 숫자:"))
        self.layout.AddRow(self.txt)
        self.layout.AddRow(self.cb_border)
        self.layout.AddRow(self.btn_confirm)
        
    def OnTextKeyDown(self, sender, e):
        if e.Key == forms.Keys.Enter:
            self.UpdatePreview()
            e.Handled = True
            
    def GetGeometry(self):
        if not self.txt.Text:
            return []
            
        if self.cb_border.Checked:
            return MarkGenerator.get_circled_text(self.txt.Text)
        else:
            return MarkGenerator.get_number_arranged(self.txt.Text)

# ==============================================================================
# [3. 메인 실행부]
# ==============================================================================
def main():
    while True:
        target = rs.GetObject("노면표시를 배치할 사각형 선택 (ESC: 종료)", 4)
        if not target: break
        curve = rs.coercecurve(target)
        if not curve or not curve.IsClosed:
            print("닫힌 커브를 선택해주세요.")
            continue
        amp = rg.AreaMassProperties.Compute(curve)
        center = amp.Centroid
        success, pl = curve.TryGetPolyline()
        if not success: continue
        pts = list(pl)
        v1 = pts[1] - pts[0]
        v2 = pts[3] - pts[0]
        if v1.Length >= v2.Length:
            v_forward, v_side = v1, v2
        else:
            v_forward, v_side = v2, v1
        v_forward.Unitize()
        v_side.Unitize()
        base_plane = rg.Plane(center, v_side, v_forward)
        while True:
            picker = CategoryIconPicker()
            Rhino.UI.EtoExtensions.ShowSemiModal(picker, Rhino.RhinoDoc.ActiveDoc, Rhino.UI.RhinoEtoApp.MainWindow)
            mode = getattr(picker, 'Result', None)
            if mode is None: break
            if mode == "방향표시": dlg = ArrowDialog(base_plane, mode)
            elif mode == "심볼": dlg = SymbolDialog(base_plane, mode)
            else: dlg = TextDialog(base_plane, mode)
            Rhino.UI.EtoExtensions.ShowSemiModal(dlg, Rhino.RhinoDoc.ActiveDoc, Rhino.UI.RhinoEtoApp.MainWindow)
            if getattr(dlg, 'Result', False):
                rs.EnableRedraw(False)
                layer_name = "RoadMark_" + str(mode)
                if not rs.IsLayer(layer_name): rs.AddLayer(layer_name)
                for c in dlg.conduit.curves:
                    if c and c.IsValid:
                        obj_id = Rhino.RhinoDoc.ActiveDoc.Objects.AddCurve(c)
                        rs.ObjectLayer(obj_id, layer_name)
                        rs.ObjectColor(obj_id, [255, 255, 255])
                rs.EnableRedraw(True)
                break
            else:
                continue

if __name__ == "__main__":
    main()