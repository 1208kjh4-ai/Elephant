# -*- coding: utf-8 -*-
import os
import sys
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
ELEPHANT_DIR = os.path.dirname(SCRIPT_DIR)
ICON_DIR = os.path.join(ELEPHANT_DIR, "icons")
IMG_ARROW = "arrow.png"
IMG_SYMBOL = "symbol.png"
IMG_TEXT = "text.png"

if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import roadtext.composer as _roadtext_composer
import roadtext.digits as _roadtext_digits
import roadtext.errors as _roadtext_errors
import roadtext.hangul as _roadtext_hangul
import roadtext.pictograms as _roadtext_pictograms
import roadtext.library as _roadtext_library
import roadtext.runtime as _roadtext_runtime

try:
    reload
except NameError:
    from importlib import reload

# RunPythonScript를 같은 Rhino 세션에서 다시 실행해도 수정된 엔진을 읽습니다.
for _roadtext_module in (
    _roadtext_errors,
    _roadtext_hangul,
    _roadtext_pictograms,
    _roadtext_digits,
    _roadtext_library,
    _roadtext_composer,
    _roadtext_runtime,
):
    reload(_roadtext_module)

RoadTextComposer = _roadtext_composer.RoadTextComposer
RoadTextError = _roadtext_errors.RoadTextError
create_digit_curves = _roadtext_digits.create_digit_curves
has_digit = _roadtext_digits.has_digit
PICTOGRAM_LABELS = list(_roadtext_pictograms.PICTOGRAM_LABELS)
get_pictogram_layer_name = _roadtext_pictograms.get_layer_name
get_road_glyph_library = _roadtext_runtime.get_road_glyph_library
reset_road_glyph_library = _roadtext_runtime.reset_road_glyph_library

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
# [2. 통합 지오메트리 엔진]
# ==============================================================================
class MarkGenerator:
    W, H = 1000, 3000
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
    def get_number_arranged(input_str):
        combined_curves = []
        digits = [c for c in input_str if has_digit(c)]
        if not digits: return []
        gap = 100
        total_width = (len(digits) * MarkGenerator.W) + ((len(digits)-1) * gap)
        start_x = -total_width / 2.0
        for i, char in enumerate(digits):
            x_offset = start_x + (i * (MarkGenerator.W + gap))
            move = rg.Transform.Translation(x_offset, -1500.0, 0.0)
            for curve in create_digit_curves(char):
                curve.Transform(move)
                combined_curves.append(curve)
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

    def CalculateBoundingBox(self, e):
        bbox = rg.BoundingBox.Empty
        for curve in self.curves:
            if curve and curve.IsValid:
                bbox.Union(curve.GetBoundingBox(True))
        if bbox.IsValid:
            e.IncludeBoundingBox(bbox)

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
    def __init__(self, base_plane, mode, target_width=None, target_height=None):
        self.Title = "세부 설정 - " + mode
        self.base_plane = base_plane
        self.target_width = target_width
        self.target_height = target_height
        self.last_preview_error = None
        
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
        
    def OnPreviewError(self, message):
        self.btn_ok.Enabled = False

    def OnPreviewReady(self, has_geometry):
        pass

    def UpdatePreview(self):
        self.last_preview_error = None
        try:
            parts = self.GetGeometry()
        except RoadTextError as error:
            self.last_preview_error = error.message_text
            self.conduit.curves = []
            self.OnPreviewError(error.message_text)
            Rhino.RhinoDoc.ActiveDoc.Views.Redraw()
            return False
        
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
        self.OnPreviewReady(len(self.conduit.curves) > 0)
        Rhino.RhinoDoc.ActiveDoc.Views.Redraw()
        return len(self.conduit.curves) > 0
        
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
        self.list = forms.ListBox()
        self.list.DataStore = PICTOGRAM_LABELS
        self.list.SelectedIndex = 0
        self.list.SelectedIndexChanged += lambda sender, e: self.UpdatePreview()
        self.lbl_status = forms.Label(
            Text=u"픽토그램을 선택하세요.",
            TextColor=drawing.Colors.Gray
        )
        self.layout.AddRow(forms.Label(Text=u"교통 픽토그램 선택:"))
        self.layout.AddRow(self.list)
        self.layout.AddRow(self.lbl_status)

    def OnPreviewError(self, message):
        BaseMarkDialog.OnPreviewError(self, message)
        self.lbl_status.Text = (
            message.splitlines()[0] if message else u"픽토그램 생성 실패"
        )
        self.lbl_status.TextColor = drawing.Colors.Red

    def OnPreviewReady(self, has_geometry):
        self.btn_ok.Enabled = has_geometry
        if has_geometry:
            self.lbl_status.Text = u"픽토그램 프리뷰가 갱신되었습니다."
            self.lbl_status.TextColor = drawing.Colors.DodgerBlue

    def GetGeometry(self):
        label = self.list.SelectedValue
        layer_name = get_pictogram_layer_name(label)
        if not layer_name:
            raise RoadTextError(
                u"등록되지 않은 픽토그램입니다: {0}".format(label)
            )

        library = get_road_glyph_library()
        curves = library.duplicate_glyph(layer_name)
        if not curves:
            raise RoadTextError(
                u"픽토그램 글리프를 찾을 수 없습니다.\n\n"
                u"표시 이름: {0}\n"
                u"누락 레이어: {1}".format(label, layer_name)
            )
        return curves

class TextDialog(BaseMarkDialog):
    """기존 숫자와 통합 도로문자를 함께 제공하는 대화상자입니다."""

    def SetupUI(self):
        self.rb_number = forms.RadioButton(Text=u"숫자")
        self.rb_roadtext = forms.RadioButton(
            self.rb_number,
            Text=u"통합 도로문자"
        )
        mode_layout = forms.DynamicLayout()
        mode_layout.BeginHorizontal()
        mode_layout.Add(self.rb_number)
        mode_layout.Add(self.rb_roadtext)
        mode_layout.EndHorizontal()

        self.lbl_input = forms.Label(Text=u"표시할 숫자:")
        self.txt = forms.TextArea()
        self.txt.Height = 72
        self.txt.Wrap = False
        self.txt.AcceptsReturn = True
        self.txt.AcceptsTab = False
        self.txt.KeyDown += self.OnTextKeyDown

        self.lbl_input_hint = forms.Label(
            Text=u"Enter: 적용",
            TextColor=drawing.Colors.Gray
        )

        initial_width = (
            self.target_width
            if self.target_width is not None and self.target_width > 0.0
            else 3000.0
        )
        self.lbl_max_width = forms.Label(Text=u"글자 배치 최대폭:")
        self.txt_max_width = forms.TextBox(
            Text=u"{0:g}".format(initial_width)
        )
        self.txt_max_width.Enabled = False
        self.txt_max_width.KeyDown += self.OnNumericSettingKeyDown

        self.lbl_letter_gap = forms.Label(Text=u"자간:")
        self.txt_letter_gap = forms.TextBox(Text=u"100")
        self.txt_letter_gap.Enabled = False
        self.txt_letter_gap.KeyDown += self.OnNumericSettingKeyDown

        self.lbl_alignment = forms.Label(Text=u"문자 정렬:")
        self.rb_align_center = forms.RadioButton(Text=u"가운데 정렬")
        self.rb_align_justify = forms.RadioButton(
            self.rb_align_center,
            Text=u"양쪽 정렬"
        )
        self.rb_align_center.Checked = True
        self.rb_align_center.Enabled = False
        self.rb_align_justify.Enabled = False
        self.rb_align_justify.CheckedChanged += (
            lambda sender, e: self.UpdatePreview()
        )

        alignment_layout = forms.DynamicLayout()
        alignment_layout.BeginHorizontal()
        alignment_layout.Add(self.rb_align_center)
        alignment_layout.Add(self.rb_align_justify)
        alignment_layout.EndHorizontal()

        self.cb_border = forms.CheckBox(
            Text=u"원형 테두리 적용 (속도표시)"
        )
        self.cb_border.CheckedChanged += lambda sender, e: self.UpdatePreview()

        self.btn_confirm = forms.Button(Text=u"텍스트 적용")
        self.btn_confirm.Click += self.OnApplyText

        self.lbl_text_status = forms.Label(
            Text=u"문자를 입력하고 Enter 또는 텍스트 적용을 누르세요.",
            TextColor=drawing.Colors.Gray
        )
        self.btn_ok.Enabled = False

        self.layout.AddRow(forms.Label(Text=u"문자 종류:"), mode_layout)
        self.layout.AddRow(self.lbl_input)
        self.layout.AddRow(self.txt)
        self.layout.AddRow(self.lbl_input_hint)
        self.layout.AddRow(self.lbl_max_width, self.txt_max_width)
        self.layout.AddRow(self.lbl_letter_gap, self.txt_letter_gap)
        self.layout.AddRow(self.lbl_alignment, alignment_layout)
        self.layout.AddRow(self.cb_border)
        self.layout.AddRow(self.btn_confirm)
        self.layout.AddRow(self.lbl_text_status)

        self.rb_roadtext.Checked = True
        self.rb_roadtext.CheckedChanged += self.OnTextModeChanged
        self.OnTextModeChanged(None, None)

    def IsRoadTextMode(self):
        return bool(self.rb_roadtext.Checked)

    def OnTextModeChanged(self, sender, e):
        road_text_mode = self.IsRoadTextMode()
        if road_text_mode:
            self.lbl_input.Text = u"표시할 도로문자:"
            self.lbl_input_hint.Text = (
                u"Enter: 적용 / Shift+Enter: 줄바꿈"
            )
            self.cb_border.Checked = False
        else:
            self.lbl_input.Text = u"표시할 숫자:"
            self.lbl_input_hint.Text = u"Enter: 적용"

        self.cb_border.Enabled = not road_text_mode
        self.lbl_max_width.Enabled = road_text_mode
        self.txt_max_width.Enabled = road_text_mode
        self.lbl_letter_gap.Enabled = road_text_mode
        self.txt_letter_gap.Enabled = road_text_mode
        self.lbl_alignment.Enabled = road_text_mode
        self.rb_align_center.Enabled = road_text_mode
        self.rb_align_justify.Enabled = road_text_mode
        self.UpdatePreview()

    def OnApplyText(self, sender, e):
        if self.IsRoadTextMode():
            self.txt.Text = RoadTextComposer.normalize_text(self.txt.Text)

        if not self.UpdatePreview() and self.last_preview_error:
            title = (
                u"통합 도로문자"
                if self.IsRoadTextMode()
                else u"숫자 도로표시"
            )
            rs.MessageBox(self.last_preview_error, 0, title)

    def OnTextKeyDown(self, sender, e):
        if e.Key == forms.Keys.Enter:
            if self.IsRoadTextMode() and e.Shift:
                return
            self.OnApplyText(sender, e)
            e.Handled = True

    def OnNumericSettingKeyDown(self, sender, e):
        if e.Key == forms.Keys.Enter:
            self.OnApplyText(sender, e)
            e.Handled = True

    def GetRoadTextMaxWidth(self):
        value_text = u"{0}".format(
            self.txt_max_width.Text or u""
        ).strip().replace(u",", u"")
        try:
            max_width = float(value_text)
        except (TypeError, ValueError):
            raise RoadTextError(u"글자 배치 최대폭은 숫자로 입력해주세요.")
        if max_width <= 0.0:
            raise RoadTextError(u"글자 배치 최대폭은 0보다 커야 합니다.")
        return max_width

    def GetRoadTextLetterGap(self):
        value_text = u"{0}".format(
            self.txt_letter_gap.Text or u""
        ).strip().replace(u",", u"")
        try:
            letter_gap = float(value_text)
        except (TypeError, ValueError):
            raise RoadTextError(u"자간은 숫자로 입력해주세요.")
        if letter_gap < 0.0:
            raise RoadTextError(u"자간은 0 이상이어야 합니다.")
        return letter_gap

    def GetRoadTextAlignment(self):
        if self.rb_align_justify.Checked:
            return "justify"
        return "center"

    def OnPreviewError(self, message):
        BaseMarkDialog.OnPreviewError(self, message)
        first_line = message.splitlines()[0] if message else u"생성 실패"
        self.lbl_text_status.Text = first_line
        self.lbl_text_status.TextColor = drawing.Colors.Red

    def OnPreviewReady(self, has_geometry):
        self.btn_ok.Enabled = has_geometry
        if has_geometry:
            if self.IsRoadTextMode():
                self.lbl_text_status.Text = u"통합 도로문자 프리뷰가 갱신되었습니다."
            else:
                self.lbl_text_status.Text = u"숫자 프리뷰가 갱신되었습니다."
            self.lbl_text_status.TextColor = drawing.Colors.DodgerBlue
        elif not self.txt.Text:
            self.lbl_text_status.Text = (
                u"문자를 입력하고 Enter 또는 텍스트 적용을 누르세요."
            )
            self.lbl_text_status.TextColor = drawing.Colors.Gray

    def GetGeometry(self):
        if not self.txt.Text:
            return []

        if self.IsRoadTextMode():
            library = get_road_glyph_library()
            composer = RoadTextComposer(library)
            return composer.compose_text(
                self.txt.Text,
                self.GetRoadTextMaxWidth(),
                self.GetRoadTextAlignment(),
                self.GetRoadTextLetterGap()
            )

        invalid_chars = [
            char for char in self.txt.Text
            if char not in u"0123456789"
        ]
        if invalid_chars:
            raise RoadTextError(u"숫자 입력기에서는 0~9만 입력할 수 있습니다.")

        if self.cb_border.Checked:
            return MarkGenerator.get_circled_text(self.txt.Text)
        return MarkGenerator.get_number_arranged(self.txt.Text)

# ==============================================================================
# [4. 최종 Curve 생성]
# ==============================================================================
def bake_mark_curves(curves, layer_name):
    """프리뷰 Curve 전체를 하나의 Undo 기록으로 문서에 추가합니다."""
    if not curves:
        return []

    doc = Rhino.RhinoDoc.ActiveDoc
    created_ids = []
    undo_id = doc.BeginUndoRecord("Create Road Mark")

    try:
        layer_index = doc.Layers.FindByFullPath(layer_name, -1)
        if layer_index < 0:
            layer = Rhino.DocObjects.Layer()
            layer.Name = layer_name
            layer.Color = System.Drawing.Color.White
            layer_index = doc.Layers.Add(layer)

        if layer_index < 0:
            raise RoadTextError(
                u"결과 레이어를 만들 수 없습니다: {0}".format(layer_name)
            )

        attributes = Rhino.DocObjects.ObjectAttributes()
        attributes.LayerIndex = layer_index
        attributes.ColorSource = (
            Rhino.DocObjects.ObjectColorSource.ColorFromObject
        )
        attributes.ObjectColor = System.Drawing.Color.White

        for curve in curves:
            if curve is None or not curve.IsValid:
                continue
            object_id = doc.Objects.AddCurve(curve, attributes)
            if object_id == System.Guid.Empty:
                raise RoadTextError(u"도로표시 Curve를 문서에 추가하지 못했습니다.")
            created_ids.append(object_id)

        if not created_ids:
            raise RoadTextError(u"생성된 도로표시 Curve가 없습니다.")
    except Exception:
        for object_id in created_ids:
            doc.Objects.Delete(object_id, True)
        raise
    finally:
        if undo_id > 0:
            doc.EndUndoRecord(undo_id)

    doc.Views.Redraw()
    return created_ids


# ==============================================================================
# [5. 배치 기준 입력]
# ==============================================================================
def get_placement_mode():
    getter = Rhino.Input.Custom.GetOption()
    getter.SetCommandPrompt(
        u"배치 방식 선택 (Rectangle=사각형, TwoPoint=두 점) <Rectangle>"
    )
    getter.AcceptNothing(True)

    rectangle_index = getter.AddOption("Rectangle")
    two_point_index = getter.AddOption("TwoPoint")
    result = getter.Get()

    if result == Rhino.Input.GetResult.Nothing:
        return "rectangle"
    if result != Rhino.Input.GetResult.Option:
        return None

    option_index = getter.OptionIndex()
    if option_index == rectangle_index:
        return "rectangle"
    if option_index == two_point_index:
        return "two_point"
    return None


def get_rectangle_placement():
    while True:
        target = rs.GetObject(
            "노면표시를 배치할 사각형 선택 (ESC: 종료)",
            4
        )
        if not target:
            return None

        curve = rs.coercecurve(target)
        if not curve or not curve.IsClosed:
            print("닫힌 커브를 선택해주세요.")
            continue

        amp = rg.AreaMassProperties.Compute(curve)
        success, polyline = curve.TryGetPolyline()
        if amp is None or not success:
            print("폴리라인 사각형을 선택해주세요.")
            continue

        points = list(polyline)
        if len(points) < 4:
            print("폴리라인 사각형을 선택해주세요.")
            continue

        v1 = points[1] - points[0]
        v2 = points[3] - points[0]
        if v1.Length >= v2.Length:
            v_forward, v_side = v1, v2
        else:
            v_forward, v_side = v2, v1

        target_height = v_forward.Length
        target_width = v_side.Length
        v_forward.Unitize()
        v_side.Unitize()
        base_plane = rg.Plane(amp.Centroid, v_side, v_forward)
        return base_plane, target_width, target_height


def create_two_point_plane(first_point, direction_point, tolerance):
    origin = rg.Point3d(first_point)
    y_axis = rg.Vector3d(
        direction_point.X - origin.X,
        direction_point.Y - origin.Y,
        0.0
    )

    if y_axis.Length <= tolerance:
        return None

    y_axis.Unitize()
    x_axis = rg.Vector3d.CrossProduct(y_axis, rg.Vector3d.ZAxis)
    return rg.Plane(origin, x_axis, y_axis)


def get_two_point_placement():
    first_point = rs.GetPoint("노면표시 배치 원점 선택 (ESC: 종료)")
    if first_point is None:
        return None

    doc = Rhino.RhinoDoc.ActiveDoc
    tolerance = doc.ModelAbsoluteTolerance if doc else 0.001

    while True:
        direction_point = rs.GetPoint(
            "XY 평면 기준 +Y 방향점 선택 (ESC: 종료)",
            first_point
        )
        if direction_point is None:
            return None

        base_plane = create_two_point_plane(
            first_point,
            direction_point,
            tolerance
        )
        if base_plane is not None:
            return base_plane, None, None

        Rhino.RhinoApp.WriteLine(
            u"두 점의 XY 위치가 너무 가깝습니다. 방향점을 다시 선택하세요."
        )


def get_placement(placement_mode):
    if placement_mode == "two_point":
        return get_two_point_placement()
    return get_rectangle_placement()


# ==============================================================================
# [6. 메인 실행부]
# ==============================================================================
def main():
    reset_road_glyph_library()

    placement_mode = get_placement_mode()
    if placement_mode is None:
        return

    while True:
        placement = get_placement(placement_mode)
        if placement is None:
            break
        base_plane, target_width, target_height = placement

        while True:
            picker = CategoryIconPicker()
            Rhino.UI.EtoExtensions.ShowSemiModal(picker, Rhino.RhinoDoc.ActiveDoc, Rhino.UI.RhinoEtoApp.MainWindow)
            mode = getattr(picker, 'Result', None)
            if mode is None: break
            if mode == "방향표시":
                dlg = ArrowDialog(
                    base_plane, mode, target_width, target_height
                )
            elif mode == "심볼":
                dlg = SymbolDialog(
                    base_plane, mode, target_width, target_height
                )
            else:
                dlg = TextDialog(
                    base_plane, mode, target_width, target_height
                )
            Rhino.UI.EtoExtensions.ShowSemiModal(dlg, Rhino.RhinoDoc.ActiveDoc, Rhino.UI.RhinoEtoApp.MainWindow)
            if getattr(dlg, 'Result', False):
                rs.EnableRedraw(False)
                try:
                    layer_name = "RoadMark_" + str(mode)
                    bake_mark_curves(dlg.conduit.curves, layer_name)
                    break
                except RoadTextError as error:
                    rs.MessageBox(error.message_text, 0, "도로표시 생성")
                    continue
                except Exception as error:
                    rs.MessageBox(
                        u"도로표시 생성 중 오류가 발생했습니다.\n\n{0}".format(
                            error
                        ),
                        0,
                        "도로표시 생성"
                    )
                    continue
                finally:
                    rs.EnableRedraw(True)
            else:
                continue

if __name__ == "__main__":
    main()
