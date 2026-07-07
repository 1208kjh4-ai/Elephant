# -*- coding: utf-8 -*-
"""
SHP Generic Importer for Rhino 8
--------------------------------
- Select one SHP file
- Read geometry + DBF attributes
- Bake geometry by SHP type:
    Point / MultiPoint  -> Rhino Points
    PolyLine           -> Rhino Curves
    Polygon            -> Planar Breps when possible, fallback to boundary curves
    Z variants         -> Preserve Z values if present
- Store DBF record values as Rhino Object User Text
- Built-in NGII standard feature-code map for automatic Korean layer naming

Requirement:
    pyshp module as shapefile.py must be available to Rhino Python.
"""

import os
import re
import traceback

import Rhino
import Rhino.Geometry as rg
import Rhino.DocObjects as rd
import rhinoscriptsyntax as rs
import scriptcontext as sc
import System

try:
    import shapefile
except Exception:
    shapefile = None


# ----------------------------------------------------------------------
# Basic settings
# ----------------------------------------------------------------------
TOL = sc.doc.ModelAbsoluteTolerance if sc.doc else 0.001

ENCODING_CANDIDATES = [
    "cp949",
    "euc-kr",
    "utf-8",
    "utf-8-sig",
    "latin1",
]

# ESRI Shapefile type codes
NULL_SHAPE = 0
POINT = 1
POLYLINE = 3
POLYGON = 5
MULTIPOINT = 8
POINTZ = 11
POLYLINEZ = 13
POLYGONZ = 15
MULTIPOINTZ = 18
POINTM = 21
POLYLINEM = 23
POLYGONM = 25
MULTIPOINTM = 28
MULTIPATCH = 31

POINT_TYPES = set([POINT, POINTZ, POINTM])
MULTIPOINT_TYPES = set([MULTIPOINT, MULTIPOINTZ, MULTIPOINTM])
POLYLINE_TYPES = set([POLYLINE, POLYLINEZ, POLYLINEM])
POLYGON_TYPES = set([POLYGON, POLYGONZ, POLYGONM])

# ----------------------------------------------------------------------
# Built-in layer code mapping
# Source: 별표1 수치지도 지형지물 표준코드.xls
# Structure: 통합코드 -> 소분류(지형지물명)
# ----------------------------------------------------------------------
STANDARD_CODE_MAP = {
    u"A0010000": u"도로경계(미분류)",
    u"A0013110": u"(기존도로)미분류",
    u"A0013111": u"(기존도로)고속국도",
    u"A0013112": u"(기존도로)일반국도",
    u"A0013113": u"(기존도로)지방도",
    u"A0013114": u"(기존도로)특별시도ㆍ광역시도",
    u"A0013115": u"(기존도로)시도",
    u"A0013116": u"(기존도로)군도",
    u"A0013117": u"(기존도로)면리간도로",
    u"A0013118": u"부지안도로",
    u"A0013122": u"터널안도로",
    u"A0013130": u"(건설예정도로)미분류",
    u"A0013131": u"(건설예정도로)고속국도",
    u"A0013132": u"(건설예정도로)일반국도",
    u"A0013133": u"(건설예정도로)지방도",
    u"A0013134": u"(건설예정도로)특별시도ㆍ 광역시도",
    u"A0013135": u"(건설예정도로)시도",
    u"A0013136": u"(건설예정도로)군도",
    u"A0013137": u"(건설예정도로)면리간도로",
    u"A0013140": u"(건설중도로)미분류",
    u"A0013141": u"(건설중도로)고속국도",
    u"A0013142": u"(건설중도로)일반국도",
    u"A0013143": u"(건설중도로)지방도",
    u"A0013144": u"(건설중도로)특별시도ㆍ 광역시도",
    u"A0013145": u"(건설중도로)시도",
    u"A0013146": u"(건설중도로)군도",
    u"A0013147": u"(건설중도로)면리간도로",
    u"A0013360": u"(편의시설)미분류",
    u"A0013370": u"(기타)미분류",
    u"A0013430": u"(도로번호-기호)미분류",
    u"A0013431": u"(도로번호-기호)고속국도",
    u"A0013432": u"(도로번호-기호)일반국도",
    u"A0013433": u"(도로번호-기호)지방도",
    u"A0013434": u"(도로번호-기호)특별시도",
    u"A0013435": u"(도로번호-기호)시도",
    u"A0013436": u"(도로번호-기호)군도",
    u"A0013440": u"(도로번호)미분류",
    u"A0013441": u"(도로번호)고속국도",
    u"A0013442": u"(도로번호)일반국도",
    u"A0013443": u"(도로번호)지방도",
    u"A0013444": u"(도로번호)특별시도",
    u"A0013445": u"(도로번호)시도",
    u"A0013446": u"(도로번호)군도",
    u"A0020000": u"도로중심선(미분류)",
    u"A0023119": u"소로",
    u"A0023210": u"(도로중심선)미분류",
    u"A0023211": u"(도로중심선)고속국도",
    u"A0023212": u"(도로중심선)일반국도",
    u"A0023213": u"(도로중심선)지방도",
    u"A0023214": u"(도로중심선)특별시도ㆍ 광역시도",
    u"A0023215": u"(도로중심선)시도",
    u"A0023216": u"(도로중심선)군도",
    u"A0023217": u"(도로중심선)면리간도로",
    u"A0033320": u"인도(미분류)",
    u"A0033324": u"인도",
    u"A0033327": u"자전거도로",
    u"A0043325": u"횡단보도",
    u"A0053326": u"안전지대",
    u"A0063321": u"육교",
    u"A0070000": u"교량(미분류)",
    u"A0073340": u"(다리)미분류",
    u"A0073341": u"(다리)콘크리트교",
    u"A0073342": u"(다리)강교",
    u"A0073343": u"(다리)목교",
    u"A0071210": u"(철교)미분류",
    u"A0071211": u"철교",
    u"A0071212": u"(철교)고가부",
    u"A0071213": u"철도터널",
    u"A0080000": u"교차로",
    u"A0090000": u"입체교차부(미분류)",
    u"A0093350": u"(입체교차부)미분류",
    u"A0093351": u"(입체교차부)고가차도",
    u"A0093352": u"(입체교차부)지하차도",
    u"A0100000": u"인터체인지",
    u"A0110020": u"터널",
    u"A0123373": u"터널입구",
    u"A0131122": u"정거장",
    u"A0140000": u"정류장(미분류)",
    u"A0143410": u"(정류장)미분류",
    u"A0143411": u"(정류장)버스정류장",
    u"A0143412": u"(정류장)택시정류장",
    u"A0150000": u"철도(미분류)",
    u"A0151110": u"(실폭선로)미분류",
    u"A0151111": u"(실폭선로)보통 철도",
    u"A0151112": u"(실폭선로)특수 철도",
    u"A0151113": u"(실폭선로)터널안 철도",
    u"A0151114": u"(실폭선로)건설중 철도",
    u"A0151115": u"지하철(지하부)",
    u"A0151116": u"지하철(지상부)",
    u"A0151117": u"삭도",
    u"A0151118": u"고가부(도로시설)",
    u"A0151120": u"(도면제작용선로)미분류",
    u"A0151121": u"복선철도",
    u"A0151123": u"궤도(모노레일)",
    u"A0151224": u"지하철역 출입구",
    u"A0151220": u"(편의시설,기타)미분류",
    u"A0160024": u"철도부지선",
    u"A0171119": u"철도중심선",
    u"A0180000": u"철도전차대",
    u"A0191221": u"플랫폼",
    u"A0201222": u"플랫폼의 지붕",
    u"A0210000": u"나루(미분류)",
    u"A0212255": u"나루(사람)",
    u"A0212256": u"나루(차량)",
    u"A0222257": u"나루노선",
    u"B0010000": u"건물경계(미분류)",
    u"B0014110": u"(건물경계)미분류",
    u"B0014111": u"주택외건물",
    u"B0014112": u"주택",
    u"B0014113": u"연립주택",
    u"B0014114": u"공사중건물",
    u"B0014115": u"아파트",
    u"B0014116": u"무벽건물",
    u"B0014117": u"온실",
    u"B0014118": u"가건물",
    u"B0014119": u"집단가옥경계",
    u"B0014210": u"(지방행정)미분류",
    u"B0014211": u"특별시청",
    u"B0014212": u"광역시청",
    u"B0014213": u"도청",
    u"B0014214": u"시청",
    u"B0014215": u"군청",
    u"B0014216": u"구청",
    u"B0014217": u"읍사무소",
    u"B0014218": u"주민센터",
    u"B0014219": u"면사무소",
    u"B0014220": u"(치안행정)미분류",
    u"B0014221": u"법원",
    u"B0014222": u"경찰청",
    u"B0014223": u"경찰서",
    u"B0014224": u"파출소,지서",
    u"B0014225": u"교도소,구치소",
    u"B0014226": u"소년원",
    u"B0014230": u"(기타행정1)미분류",
    u"B0014231": u"소방서",
    u"B0014232": u"보건소",
    u"B0014233": u"세무서",
    u"B0014234": u"세관",
    u"B0014235": u"우체국",
    u"B0014236": u"기상대, 측후소",
    u"B0014237": u"전화국",
    u"B0014238": u"병무청",
    u"B0014240": u"(기타행정2)미분류",
    u"B0014241": u"기타관공서",
    u"B0014242": u"농업기술센터",
    u"B0014243": u"지방산림청",
    u"B0014250": u"(정부투자기관)미분류",
    u"B0014251": u"한국전력공사",
    u"B0014253": u"한국수자원공사",
    u"B0014254": u"한국도로공사",
    u"B0014255": u"한국토지주택공사",
    u"B0014257": u"한국가스공사",
    u"B0014258": u"한국농어촌공사",
    u"B0014310": u"(공업)미분류",
    u"B0014311": u"공 장",
    u"B0014312": u"발전소",
    u"B0014313": u"변전소",
    u"B0014320": u"(상업)미분류",
    u"B0014321": u"시장",
    u"B0014322": u"백화점",
    u"B0014323": u"관광음식점",
    u"B0014324": u"시장경계",
    u"B0014330": u"(농업기타)미분류",
    u"B0014331": u"양수장",
    u"B0014332": u"배수장",
    u"B0014333": u"양배수장",
    u"B0014334": u"취수장",
    u"B0014335": u"축사",
    u"B0014336": u"종축장",
    u"B0014337": u"도축장",
    u"B0014338": u"정미소",
    u"B0014339": u"정수장",
    u"B0014340": u"(하수처리)미분류",
    u"B0014341": u"하수종말처리장기호",
    u"B0014342": u"공단폐수처리장기호",
    u"B0014343": u"축산폐수처리장기호",
    u"B0014344": u"농공단지오폐수기호",
    u"B0014345": u"간이오수처리장기호",
    u"B0014346": u"분뇨처리장기호",
    u"B0014410": u"(교육,체육)미분류",
    u"B0014411": u"학교",
    u"B0014412": u"유치원, 유아원",
    u"B0014413": u"도서관",
    u"B0014414": u"실내체육관",
    u"B0014415": u"실내수영장",
    u"B0014416": u"학원",
    u"B0014417": u"기숙사",
    u"B0014420": u"(문화종교)미분류",
    u"B0014421": u"교회",
    u"B0014422": u"성당",
    u"B0014423": u"절",
    u"B0014424": u"기타종교시설",
    u"B0014425": u"박물관",
    u"B0014426": u"미술관",
    u"B0014427": u"공회당",
    u"B0014430": u"(언론기관)미분류",
    u"B0014431": u"TV방송국",
    u"B0014432": u"라디오 방송국",
    u"B0014433": u"신문사",
    u"B0014434": u"잡지사",
    u"B0014435": u"CATV방송국",
    u"B0014510": u"(숙박)미분류",
    u"B0014511": u"호텔",
    u"B0014512": u"여관",
    u"B0014513": u"콘도미니엄",
    u"B0014514": u"목욕탕",
    u"B0014520": u"(운수,창고)미분류",
    u"B0014521": u"역",
    u"B0014522": u"고속버스터미널",
    u"B0014523": u"시외버스터미널",
    u"B0014524": u"창고",
    u"B0014525": u"공항",
    u"B0014526": u"자동차정비수리소",
    u"B0014527": u"세차장",
    u"B0014530": u"(금융,조합)미분류",
    u"B0014531": u"은행",
    u"B0014532": u"협동조합",
    u"B0014533": u"기타금융기관",
    u"B0014534": u"보험회사",
    u"B0014610": u"(병원)미분류",
    u"B0014611": u"일반병원",
    u"B0014612": u"결핵병원",
    u"B0014613": u"나병원",
    u"B0014614": u"정신병원",
    u"B0014615": u"약국",
    u"B0014620": u"(아동복지시설)미분류",
    u"B0014621": u"유아시설",
    u"B0014622": u"아동상담소",
    u"B0014623": u"자립지원시설",
    u"B0014624": u"탁아시설",
    u"B0014625": u"영아시설",
    u"B0014626": u"아동일시보호시설",
    u"B0014627": u"아동직업보도시설",
    u"B0014630": u"(사회복지시설)미분류",
    u"B0014631": u"양로시설",
    u"B0014632": u"장애인재활시설",
    u"B0014633": u"모자보호시설",
    u"B0014634": u"미혼모시설",
    u"B0014635": u"노인복지회관",
    u"B0014636": u"부녀복지관",
    u"B0014637": u"사회복지관",
    u"B0020000": u"담장(미분류)",
    u"B0024120": u"(담장)미분류",
    u"B0024121": u"콘크리트돌담",
    u"B0024122": u"판자담",
    u"B0024123": u"생울타리",
    u"B0024124": u"흙담",
    u"B0024125": u"철조망",
    u"B0024126": u"철책",
    u"B0024127": u"문주",
    u"C0010000": u"댐(미분류)",
    u"C0012216": u"댐 (상단)",
    u"C0012217": u"댐 (하단)",
    u"C0025336": u"기중기",
    u"C0032254": u"선착장",
    u"C0040000": u"선거",
    u"C0050000": u"제방(미분류)",
    u"C0052210": u"(제방)미분류",
    u"C0052211": u"콘크리트제방(상단)",
    u"C0052212": u"콘크리트제방(하단)",
    u"C0052213": u"흙제방(상단)",
    u"C0052214": u"흙제방(하단)",
    u"C0052215": u"기호제방",
    u"C0052220": u"(방조제)미분류",
    u"C0052221": u"콘크리트방조제(상단)",
    u"C0052222": u"콘크리트방조제(하단)",
    u"C0052223": u"흙방조제(상단)",
    u"C0052224": u"흙방조제(하단)",
    u"C0052225": u"기호방조제",
    u"C0052230": u"(방파제)미분류",
    u"C0052231": u"방파제 (상단)",
    u"C0052232": u"방파제 (하단)",
    u"C0052233": u"소파블럭",
    u"C0052234": u"기호방파제",
    u"C0060000": u"수문(미분류)",
    u"C0062240": u"(수문)미분류",
    u"C0062241": u"수문",
    u"C0062242": u"배수갑문",
    u"C0062243": u"보",
    u"C0070000": u"암거(미분류)",
    u"C0076110": u"(배수시설)미분류",
    u"C0076116": u"암거",
    u"C0076117": u"측구",
    u"C0080000": u"잔교(미분류)",
    u"C0082250": u"잔교(미분류)",
    u"C0082251": u"잔교(콘크리트)",
    u"C0082252": u"잔교(목재)",
    u"C0082253": u"잔교(떠있는것)",
    u"C0090000": u"우물/약수터(미분류)",
    u"C0096310": u"지하수(미분류)",
    u"C0096311": u"우물",
    u"C0106312": u"관정",
    u"C0116313": u"분수",
    u"C0125335": u"온천",
    u"C0130000": u"양식장(미분류)",
    u"C0132327": u"양어장",
    u"C0136357": u"양식장기호",
    u"C0136358": u"양식장경계",
    u"C0142263": u"낚시터",
    u"C0152261": u"해수욕장기호",
    u"C0160000": u"등대(미분류)",
    u"C0166233": u"등대(유간수)",
    u"C0166234": u"등대(무간수)",
    u"C0166235": u"항공등대",
    u"C0170000": u"저장조(미분류)",
    u"C0176320": u"(저장시설)미분류",
    u"C0176321": u"저수조",
    u"C0176322": u"저유조",
    u"C0176323": u"기타저장조",
    u"C0186115": u"탱크",
    u"C0190000": u"광산(미분류)",
    u"C0195330": u"(광산)미분류",
    u"C0195334": u"광산",
    u"C0200000": u"적치장(미분류)",
    u"C0200120": u"적치장",
    u"C0205340": u"(매립 기타)미분류",
    u"C0205341": u"공지",
    u"C0205342": u"적치장",
    u"C0205343": u"토사매립지",
    u"C0205344": u"폐기물매립지",
    u"C0205345": u"쓰레기매립지",
    u"C0210000": u"채취장(미분류)",
    u"C0210140": u"채취장",
    u"C0215331": u"채석장",
    u"C0215332": u"토취장",
    u"C0215333": u"골재채취장",
    u"C0220000": u"조명(미분류)",
    u"C0220205": u"보조지지주",
    u"C0223367": u"가로등",
    u"C0226230": u"(조명)미분류",
    u"C0226231": u"조명등",
    u"C0226232": u"방범등",
    u"C0230000": u"전력주/통신주(미분류)",
    u"C0236240": u"(전주)미분류",
    u"C0236241": u"전화주",
    u"C0236242": u"전력주",
    u"C0236243": u"유선주",
    u"C0236244": u"공동주",
    u"C0240000": u"맨홀(미분류)",
    u"C0240016": u"지역난방맨홀",
    u"C0240017": u"송유맨홀",
    u"C0246120": u"(수송관-지상)미분류",
    u"C0246121": u"(수송관-지상)상수도",
    u"C0246122": u"(수송관-지상)하수도",
    u"C0246123": u"(수송관-지상)송유관",
    u"C0246124": u"(수송관-지상)가스관",
    u"C0246125": u"(수송관-지상)송전선",
    u"C0246126": u"(수송관-지상)통신선",
    u"C0246130": u"(수송관-지하)미분류",
    u"C0246131": u"(수송관-지하)상수도",
    u"C0246132": u"(수송관-지하)하수도",
    u"C0246133": u"(수송관-지하)송유관",
    u"C0246134": u"(수송관-지하)가스관",
    u"C0246135": u"(수송관-지하)송전선",
    u"C0246136": u"(수송관-지하)통신선",
    u"C0246340": u"(맨홀)미분류",
    u"C0246341": u"(맨홀)공동구",
    u"C0246342": u"(맨홀)가스관",
    u"C0246343": u"(맨홀)전화",
    u"C0246344": u"(맨홀)전기",
    u"C0246345": u"(맨홀)하수",
    u"C0246346": u"(맨홀)상수",
    u"C0246347": u"(맨홀)통신선",
    u"C0250000": u"소화전(미분류)",
    u"C0256324": u"소화전",
    u"C0256325": u"소화전(입상)",
    u"C0260000": u"관측소(미분류)",
    u"C0266330": u"(관측소)미분류",
    u"C0266331": u"수위관측소",
    u"C0266332": u"유량관측소",
    u"C0266333": u"우량관측소",
    u"C0266334": u"수질관측소",
    u"C0266335": u"파랑관측소",
    u"C0266336": u"풍향,풍속관측소",
    u"C0266337": u"대기오염관측소",
    u"C0270000": u"야영지",
    u"C0285311": u"묘지",
    u"C0290000": u"묘지계(미분류)",
    u"C0295113": u"묘지계",
    u"C0295312": u"공동묘지",
    u"C0295313": u"능묘",
    u"C0305316": u"유적지",
    u"C0310000": u"문화재(미분류)",
    u"C0315310": u"(문화)미분류",
    u"C0315314": u"명승고적",
    u"C0325315": u"성",
    u"C0330000": u"비석/기념비(미분류)",
    u"C0336210": u"(목표물기호1)미분류",
    u"C0336211": u"기념비",
    u"C0336212": u"묘비",
    u"C0340000": u"탑(미분류)",
    u"C0340032": u"조명탑",
    u"C0340325": u"시계탑",
    u"C0346220": u"(탑)미분류",
    u"C0346221": u"소방탑",
    u"C0346222": u"저수탑",
    u"C0346223": u"취수탑",
    u"C0346224": u"전파탑",
    u"C0346225": u"송전탑",
    u"C0346226": u"급수탑",
    u"C0350000": u"동상(미분류)",
    u"C0356213": u"동상",
    u"C0356214": u"석등",
    u"C0363361": u"공중전화",
    u"C0373362": u"우체통",
    u"C0380000": u"놀이시설(미분류)",
    u"C0380100": u"놀이시설",
    u"C0380110": u"수영장",
    u"C0382260": u"(레저,스포츠)미분류",
    u"C0382262": u"수영장기호",
    u"C0385320": u"(체육시설)미분류",
    u"C0385321": u"골프장",
    u"C0385322": u"테니스장",
    u"C0385323": u"운동장",
    u"C0385324": u"어린이놀이터",
    u"C0385325": u"스키장",
    u"C0386356": u"야외수영장",
    u"C0390000": u"계단(미분류)",
    u"C0390130": u"스텐드",
    u"C0393323": u"계단",
    u"C0403360": u"게시판(미분류)",
    u"C0403366": u"게시판",
    u"C0403426": u"광고판",
    u"C0410000": u"표지(미분류)",
    u"C0412258": u"이정표",
    u"C0413420": u"(표지)미분류",
    u"C0413421": u"도로정보판",
    u"C0413422": u"안내표지",
    u"C0413423": u"지시표지",
    u"C0413424": u"규제표지",
    u"C0413425": u"주의표지",
    u"C0423365": u"주유소",
    u"C0430000": u"주차장(미분류)",
    u"C0430230": u"주차장경계",
    u"C0433364": u"주차장",
    u"C0443363": u"휴게소",
    u"C0453322": u"지하도",
    u"C0463374": u"지하도입구",
    u"C0471220": u"지하환기구(미분류)",
    u"C0471223": u"지하철 환기통",
    u"C0476355": u"지하환기구",
    u"C0486353": u"굴뚝",
    u"C0493376": u"신호등",
    u"C0500000": u"차단기(미분류)",
    u"C0503375": u"건널목차단기",
    u"C0503377": u"가로등제어기",
    u"C0503378": u"신호등제어기",
    u"C0503379": u"전기제어기",
    u"C0513369": u"도로반사경",
    u"C0520000": u"도로분리대(미분류)",
    u"C0523120": u"(도로분리대)미분류",
    u"C0523121": u"도로분리대",
    u"C0530000": u"방지책(미분류)",
    u"C0536110": u"(구조물)미분류",
    u"C0536111": u"낙서방지책",
    u"C0536112": u"방호벽",
    u"C0536113": u"차광책",
    u"C0536114": u"소음방지책",
    u"C0536117": u"기타콘크리트구조물",
    u"C0536118": u"가드레일",
    u"C0536119": u"가드펜스",
    u"C0540000": u"요금징수소",
    u"C0556354": u"헬기장",
    u"D0010000": u"경지계(미분류)",
    u"D0015112": u"경지계",
    u"D0015210": u"(경작지)미분류",
    u"D0015211": u"논",
    u"D0015212": u"밭",
    u"D0015213": u"과수원",
    u"D0015220": u"(조경)미분류",
    u"D0015221": u"잔디",
    u"D0015222": u"화단",
    u"D0015223": u"정원수",
    u"D0020000": u"지류계(미분류)",
    u"D0023371": u"화단,가로수 보호대",
    u"D0023372": u"가로수",
    u"D0025110": u"(지류경계)미분류",
    u"D0025111": u"지류계",
    u"D0025114": u"산림계",
    u"D0025115": u"기타경계",
    u"D0025215": u"황무지",
    u"D0025216": u"조림지",
    u"D0025230": u"(산림)미분류",
    u"D0025231": u"활엽수",
    u"D0025232": u"침엽수",
    u"D0025233": u"혼합림",
    u"D0025234": u"대나무숲",
    u"D0030000": u"독립수(미분류)",
    u"D0036351": u"독립수(활엽수)",
    u"D0036352": u"독립수(침엽수)",
    u"D0040000": u"목장(미분류)",
    u"D0040001": u"목장및방목경계",
    u"D0045214": u"목초지",
    u"E0010001": u"하천경계",
    u"E0020000": u"하천중심선(미분류)",
    u"E0022110": u"(하천)미분류",
    u"E0022115": u"하천중심선",
    u"E0022112": u"세류",
    u"E0022113": u"건천",
    u"E0032111": u"실폭하천",
    u"E0042326": u"유수방향",
    u"E0052114": u"호수, 저수지",
    u"E0060000": u"용수로(미분류)",
    u"E0062270": u"(용수로)미분류",
    u"E0062271": u"공업용수로(지상)",
    u"E0062272": u"공업용수로(지하)",
    u"E0062273": u"농업용수로(지상)",
    u"E0062274": u"농업용수로(지하)",
    u"E0062275": u"도수터널",
    u"E0072325": u"폭포",
    u"E0080000": u"해안선(미분류)",
    u"E0082120": u"(바다)미분류",
    u"E0082121": u"해안선(육지)",
    u"E0082122": u"해안선(섬)",
    u"E0082123": u"등심선",
    u"E0082124": u"등심선 수치",
    u"F0010000": u"등고선(미분류)",
    u"F0017110": u"(볼록지)미분류",
    u"F0017111": u"(볼록지)주곡선",
    u"F0017112": u"(볼록지)간곡선",
    u"F0017113": u"(볼록지)조곡선",
    u"F0017114": u"(볼록지)계곡선",
    u"F0017120": u"(오목지)미분류",
    u"F0017121": u"(오목지)주곡선",
    u"F0017122": u"(오목지)간곡선",
    u"F0017123": u"(오목지)조곡선",
    u"F0017124": u"(오목지)계곡선",
    u"F0017130": u"(수치)미분류",
    u"F0017131": u"등고수치",
    u"F0020000": u"표고점(미분류)",
    u"F0027132": u"표고점수치",
    u"F0027217": u"표고점",
    u"F0030000": u"성/절토(미분류)",
    u"F0037220": u"(인공)미분류",
    u"F0037221": u"성토(상단)",
    u"F0037222": u"절토(상단)",
    u"F0037223": u"성토(하단)",
    u"F0040000": u"옹벽(미분류)",
    u"F0047224": u"콘크리트옹벽(상단)",
    u"F0047225": u"콘크리트옹벽(하단)",
    u"F0047226": u"석축(상단)",
    u"F0047227": u"석축(하단)",
    u"F0047228": u"경사보호망",
    u"F0057215": u"동굴입구",
    u"G0010000": u"행정경계(미분류)",
    u"G0010012": u"광역시계",
    u"G0010013": u"도계",
    u"G0010118": u"행정동계",
    u"G0018110": u"(행정경계선)미분류",
    u"G0018111": u"국경",
    u"G0018112": u"특별시,광역시,도",
    u"G0018113": u"시계",
    u"G0018114": u"군계",
    u"G0018115": u"구계",
    u"G0018116": u"읍계",
    u"G0018117": u"동계",
    u"G0018118": u"면계",
    u"G0018119": u"리계",
    u"G0020000": u"수부지형경계(미분류)",
    u"G0022310": u"(경계)미분류",
    u"G0022311": u"갯벌(진흙)",
    u"G0022312": u"모래",
    u"G0022313": u"습지",
    u"G0022314": u"염전",
    u"G0022315": u"용수구역",
    u"G0022316": u"집수경계(하수)",
    u"G0022317": u"수역경계(하천)",
    u"G0022318": u"댐 유역계",
    u"G0022320": u"(기호)미분류",
    u"G0022321": u"갯벌기호",
    u"G0022322": u"모래기호",
    u"G0022323": u"습지기호",
    u"G0022324": u"염전기호",
    u"G0030000": u"기타경계(미분류)",
    u"G0037210": u"(자연)미분류",
    u"G0037211": u"붕토지",
    u"G0037212": u"시태지",
    u"G0037213": u"벼랑바위",
    u"G0037214": u"너덜바위",
    u"G0037216": u"능선",
    u"G0036350": u"기타(미분류)",
    u"G0038210": u"(산업지역경계)미분류",
    u"G0038211": u"국가공업단지",
    u"G0038212": u"지방공업단지",
    u"G0038213": u"농공단지",
    u"G0038214": u"축산단지",
    u"G0038215": u"국토계획관련지역",
    u"G0038220": u"(환경지역경계)미분류",
    u"G0038221": u"자연환경보존지역",
    u"G0038222": u"자연생태계보존구역",
    u"G0038223": u"상수원보호지역",
    u"G0038224": u"개발제한구역",
    u"G0038225": u"환경보존특별 대책지역",
    u"G0038230": u"(관광문화지역)미분류",
    u"G0038231": u"문화재보호구역",
    u"G0038232": u"관광단지",
    u"G0038233": u"위락단지",
    u"G0038240": u"(주거지역경계)미분류",
    u"G0038241": u"외국인주거지역",
    u"H0010000": u"도곽(미분류)",
    u"H0010500": u"미분류",
    u"H0010601": u"난외주기",
    u"H0017334": u"도곽",
    u"H0020000": u"기준점(미분류)",
    u"H0027133": u"삼각점수치",
    u"H0027134": u"수준점수치",
    u"H0027135": u"통합기준점수치",
    u"H0027310": u"(국가기준점)미분류",
    u"H0027311": u"삼각점",
    u"H0027312": u"수준점",
    u"H0027313": u"통합기준점",
    u"H0027320": u"(항측기준점)미분류",
    u"H0027321": u"평면기준점",
    u"H0027322": u"표고기준점",
    u"H0027323": u"사진기준점",
    u"H0027330": u"(기타기준점)미분류",
    u"H0027331": u"지적",
    u"H0027332": u"수로",
    u"H0027333": u"기타",
    u"H0037335": u"격자",
    u"H0040000": u"지명(미분류)",
    u"H0040010": u"주거시설",
    u"H0040011": u"농경시설",
    u"H0040104": u"해양",
    u"H0040154": u"지형",
    u"H0040203": u"목장 및 방목",
    u"H0040205": u"경관",
    u"H0049110": u"(도로)미분류",
    u"H0049111": u"도로",
    u"H0049112": u"유료도로",
    u"H0049113": u"도로시설",
    u"H0049114": u"다리",
    u"H0049115": u"터널",
    u"H0049116": u"행선지명",
    u"H0049120": u"(철도)미분류",
    u"H0049121": u"철도",
    u"H0049122": u"철도시설",
    u"H0049123": u"철교",
    u"H0049124": u"터널",
    u"H0049125": u"행선지명",
    u"H0049130": u"(하천)미분류",
    u"H0049131": u"하천",
    u"H0049132": u"세류",
    u"H0049133": u"하천시설",
    u"H0049134": u"지하수로",
    u"H0049140": u"(건물)미분류",
    u"H0049141": u"지방행정기관",
    u"H0049142": u"치안행정기관",
    u"H0049143": u"기타행정기관",
    u"H0049144": u"산업시설",
    u"H0049145": u"문화,교육시설",
    u"H0049146": u"서비스시설",
    u"H0049147": u"의료,후생시설",
    u"H0049150": u"(지류)미분류",
    u"H0049151": u"식생",
    u"H0049152": u"평야,들",
    u"H0049154": u"변형지물,바위",
    u"H0049160": u"(시설물)미분류",
    u"H0049161": u"보조물",
    u"H0049162": u"목표물",
    u"H0049210": u"(도시지역)미분류",
    u"H0049211": u"특별시",
    u"H0049212": u"광역시",
    u"H0049213": u"도",
    u"H0049214": u"시",
    u"H0049215": u"구",
    u"H0049216": u"법정동",
    u"H0049217": u"행정동",
    u"H0049220": u"(농어촌지역)미분류",
    u"H0049221": u"도",
    u"H0049222": u"군",
    u"H0049223": u"읍",
    u"H0049224": u"면",
    u"H0049225": u"리",
    u"H0049226": u"자연부락",
    u"H0049230": u"(지역,구역명)미분류",
    u"H0049231": u"산업관련지역명",
    u"H0049232": u"환경관련지역명",
    u"H0049233": u"관광,문화관련 지역명",
    u"H0059153": u"산,산맥",
}


CURRENT_STANDARD_CODE = None
CURRENT_STANDARD_NAME = None


# ----------------------------------------------------------------------
# Utility
# ----------------------------------------------------------------------
def force_text(text, fallback=""):
    if text is None:
        return fallback
    try:
        # IronPython 2 compatibility
        return unicode(text)
    except NameError:
        try:
            return str(text)
        except Exception:
            return fallback
    except Exception:
        try:
            return str(text)
        except Exception:
            return fallback


def sanitize_name(text, fallback="SHP"):
    text = force_text(text, fallback).strip()
    if not text:
        text = fallback
    # Rhino layer names do not like some characters.
    text = re.sub(r"[\\/:*?\"<>|]", "_", text)
    text = re.sub(r"\s+", "_", text)
    return text[:80]


def extract_standard_code(source_name):
    """
    Extract the most specific NGII code from a SHP file/layer name.
    Example:
        N3A_A0010000              -> A0010000
        N3A_A0000000_A0010000    -> A0010000
    Rule:
        Use the last token matching [A-Z][0-9]{7}.
    """
    text = force_text(source_name, "").upper()
    matches = re.findall(r"[A-Z][0-9]{7}", text)
    if matches:
        return matches[-1]
    return None


def resolve_import_root_name(file_base, use_mapping=True, append_code=False):
    """
    Return (root_name, extracted_code, mapped_name).
    If mapping succeeds, root_name becomes the mapped Korean feature name.
    If append_code is True, code is appended for traceability.
    If mapping fails, old behavior is preserved: SHP_<file_base>.
    """
    clean_base = sanitize_name(file_base, "SHP")
    if not use_mapping:
        return "SHP_{}".format(clean_base), None, None

    code = extract_standard_code(file_base)
    mapped = STANDARD_CODE_MAP.get(code) if code else None
    if mapped:
        if append_code:
            return sanitize_name(u"{}_{}".format(mapped, code), clean_base), code, mapped
        return sanitize_name(mapped, clean_base), code, mapped

    return "SHP_{}".format(clean_base), code, None


def ensure_layer(layer_name, color=None):
    if not color:
        color = System.Drawing.Color.Gray
    if not rs.IsLayer(layer_name):
        rs.AddLayer(layer_name, color)
    idx = sc.doc.Layers.Find(layer_name, True)
    if idx < 0:
        idx = sc.doc.Layers.Add(layer_name, color)
    return idx


def build_attrs(layer_name, fields, record, store_user_text=True):
    attrs = rd.ObjectAttributes()
    layer_idx = ensure_layer(layer_name)
    attrs.LayerIndex = layer_idx

    if store_user_text and fields and record:
        max_len = min(len(fields), len(record))
        for i in range(max_len):
            key = sanitize_name(fields[i], "field")
            try:
                val = record[i]
                if val is None:
                    val = ""
                else:
                    val = force_text(val, "")
                attrs.SetUserString(key, val)
            except Exception:
                pass
    try:
        if CURRENT_STANDARD_CODE:
            attrs.SetUserString("SHP_StandardCode", force_text(CURRENT_STANDARD_CODE, ""))
        if CURRENT_STANDARD_NAME:
            attrs.SetUserString("SHP_StandardName", force_text(CURRENT_STANDARD_NAME, ""))
    except Exception:
        pass

    return attrs


def try_read_shapefile(path):
    if shapefile is None:
        rs.MessageBox(
            "shapefile.py 모듈을 찾을 수 없습니다.\n"
            "pyshp의 shapefile.py를 Rhino Scripts 폴더에 넣어주세요.",
            0,
            "SHP Importer"
        )
        return None, None

    last_error = None
    for enc in ENCODING_CANDIDATES:
        try:
            sf = shapefile.Reader(path, encoding=enc)
            # Force DBF read to check encoding early.
            _ = sf.records()
            return sf, enc
        except Exception as e:
            last_error = e

    # Final attempt without explicit encoding.
    try:
        sf = shapefile.Reader(path)
        _ = sf.records()
        return sf, "default"
    except Exception as e:
        last_error = e

    rs.MessageBox("SHP 파일을 읽지 못했습니다.\n\n{}".format(last_error), 0, "SHP Importer")
    return None, None


def get_fields(sf):
    # sf.fields[0] is DeletionFlag.
    fields = []
    for f in sf.fields[1:]:
        try:
            fields.append(force_text(f[0], "field"))
        except Exception:
            fields.append("field")
    return fields


def get_records_safe(sf):
    try:
        return sf.records()
    except Exception:
        return []


def get_shapes_safe(sf):
    try:
        return sf.shapes()
    except Exception:
        return []


def shape_point3d(shape, index):
    x, y = shape.points[index][0], shape.points[index][1]
    z = 0.0
    try:
        if hasattr(shape, "z") and shape.z and index < len(shape.z):
            z = float(shape.z[index])
    except Exception:
        z = 0.0
    return rg.Point3d(float(x), float(y), z)


def shape_parts_indices(shape):
    try:
        parts = list(shape.parts)
    except Exception:
        parts = [0]
    parts.append(len(shape.points))
    return parts


def polyline_curve_from_points(points, close=False):
    if len(points) < 2:
        return None
    pts = list(points)
    if close:
        if pts[0].DistanceTo(pts[-1]) > TOL:
            pts.append(pts[0])
        if len(pts) < 4:
            return None
    pl = rg.Polyline(pts)
    if not pl.IsValid:
        return None
    return pl.ToNurbsCurve()


def get_shape_type_name(shape_type):
    mapping = {
        0: "Null",
        1: "Point",
        3: "PolyLine",
        5: "Polygon",
        8: "MultiPoint",
        11: "PointZ",
        13: "PolyLineZ",
        15: "PolygonZ",
        18: "MultiPointZ",
        21: "PointM",
        23: "PolyLineM",
        25: "PolygonM",
        28: "MultiPointM",
        31: "MultiPatch",
    }
    return mapping.get(shape_type, "Unknown_{}".format(shape_type))


# ----------------------------------------------------------------------
# Bake geometry by type
# ----------------------------------------------------------------------
def bake_point_shape(shape, record, fields, root_name, store_user_text):
    layer = root_name + "_Point"
    attrs = build_attrs(layer, fields, record, store_user_text)
    count = 0
    if len(shape.points) < 1:
        return 0
    pt = shape_point3d(shape, 0)
    sc.doc.Objects.AddPoint(pt, attrs)
    count += 1
    return count


def bake_multipoint_shape(shape, record, fields, root_name, store_user_text):
    layer = root_name + "_MultiPoint"
    attrs = build_attrs(layer, fields, record, store_user_text)
    count = 0
    for i in range(len(shape.points)):
        pt = shape_point3d(shape, i)
        sc.doc.Objects.AddPoint(pt, attrs)
        count += 1
    return count


def bake_polyline_shape(shape, record, fields, root_name, store_user_text):
    layer = root_name + "_Polyline"
    attrs = build_attrs(layer, fields, record, store_user_text)
    count = 0
    parts = shape_parts_indices(shape)
    for i in range(len(parts) - 1):
        a, b = parts[i], parts[i + 1]
        if b - a < 2:
            continue
        pts = [shape_point3d(shape, j) for j in range(a, b)]
        crv = polyline_curve_from_points(pts, close=False)
        if crv:
            sc.doc.Objects.AddCurve(crv, attrs)
            count += 1
    return count


def bake_polygon_shape(shape, record, fields, root_name, store_user_text, polygon_mode):
    """
    polygon_mode:
        0 = Surface when possible + fallback boundary
        1 = Boundary curves only
    """
    raw_layer = root_name + "_Polygon_Boundary"
    surface_layer = root_name + "_Polygon_Surface"
    failed_layer = root_name + "_Polygon_Failed"

    raw_attrs = build_attrs(raw_layer, fields, record, store_user_text)
    surface_attrs = build_attrs(surface_layer, fields, record, store_user_text)
    failed_attrs = build_attrs(failed_layer, fields, record, store_user_text)

    parts = shape_parts_indices(shape)
    ring_curves = []

    for i in range(len(parts) - 1):
        a, b = parts[i], parts[i + 1]
        if b - a < 3:
            continue
        pts = [shape_point3d(shape, j) for j in range(a, b)]
        crv = polyline_curve_from_points(pts, close=True)
        if crv:
            ring_curves.append(crv)

    if not ring_curves:
        return 0, 0, 0

    boundary_count = 0
    brep_count = 0
    failed_count = 0

    if polygon_mode == 1:
        for crv in ring_curves:
            sc.doc.Objects.AddCurve(crv, raw_attrs)
            boundary_count += 1
        return boundary_count, brep_count, failed_count

    # Try planar brep creation per shape. This can preserve holes when rings are nested.
    breps = None
    try:
        breps = rg.Brep.CreatePlanarBreps(ring_curves, TOL)
    except Exception:
        breps = None

    if breps and len(breps) > 0:
        for brep in breps:
            sc.doc.Objects.AddBrep(brep, surface_attrs)
            brep_count += 1
    else:
        # Fallback: add rings as boundary curves for manual inspection.
        for crv in ring_curves:
            sc.doc.Objects.AddCurve(crv, failed_attrs)
            failed_count += 1

    return boundary_count, brep_count, failed_count


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------
def main():
    path = rs.OpenFileName("가져올 SHP 파일을 선택하세요", "Shapefiles (*.shp)|*.shp||")
    if not path:
        return

    sf, encoding = try_read_shapefile(path)
    if sf is None:
        return

    fields = get_fields(sf)
    records = get_records_safe(sf)
    shapes = get_shapes_safe(sf)

    if not shapes:
        rs.MessageBox("SHP 안에서 geometry를 찾지 못했습니다.", 0, "SHP Importer")
        return

    file_base = sanitize_name(os.path.splitext(os.path.basename(path))[0], "SHP")

    map_choice = rs.GetString(
        "내장 지형지물 표준코드로 레이어명을 치환할까요?",
        "Yes",
        ["Yes", "No"]
    )
    use_mapping = (map_choice != "No")

    append_code = False
    if use_mapping:
        append_choice = rs.GetString(
            "치환된 레이어명 뒤에 코드도 붙일까요?",
            "No",
            ["Yes", "No"]
        )
        append_code = (append_choice == "Yes")

    root_name, extracted_code, mapped_name = resolve_import_root_name(
        file_base,
        use_mapping=use_mapping,
        append_code=append_code
    )

    global CURRENT_STANDARD_CODE, CURRENT_STANDARD_NAME
    CURRENT_STANDARD_CODE = extracted_code
    CURRENT_STANDARD_NAME = mapped_name

    shape_type_name = get_shape_type_name(sf.shapeType)

    store_choice = rs.GetString(
        "DBF 속성값을 Object User Text로 저장할까요?",
        "Yes",
        ["Yes", "No"]
    )
    store_user_text = (store_choice != "No")

    polygon_mode = 0
    if sf.shapeType in POLYGON_TYPES:
        mode_choice = rs.GetString(
            "Polygon SHP 처리 방식",
            "Surface",
            ["Surface", "Boundary"]
        )
        polygon_mode = 0 if mode_choice != "Boundary" else 1

    rs.EnableRedraw(False)

    point_count = 0
    curve_count = 0
    brep_count = 0
    failed_count = 0
    null_count = 0

    try:
        for i, shape in enumerate(shapes):
            st = shape.shapeType
            if st == NULL_SHAPE:
                null_count += 1
                continue

            record = records[i] if i < len(records) else []

            if st in POINT_TYPES:
                point_count += bake_point_shape(shape, record, fields, root_name, store_user_text)

            elif st in MULTIPOINT_TYPES:
                point_count += bake_multipoint_shape(shape, record, fields, root_name, store_user_text)

            elif st in POLYLINE_TYPES:
                curve_count += bake_polyline_shape(shape, record, fields, root_name, store_user_text)

            elif st in POLYGON_TYPES:
                bnd, brp, fail = bake_polygon_shape(shape, record, fields, root_name, store_user_text, polygon_mode)
                curve_count += bnd
                brep_count += brp
                failed_count += fail

            else:
                # Unsupported types: try to bake each part as boundary curve.
                try:
                    curve_count += bake_polyline_shape(shape, record, fields, root_name + "_Unsupported", store_user_text)
                except Exception:
                    failed_count += 1

    except Exception as e:
        rs.EnableRedraw(True)
        rs.MessageBox(
            "Import 중 오류가 발생했습니다.\n\n{}\n\n{}".format(e, traceback.format_exc()),
            0,
            "SHP Importer"
        )
        return

    rs.EnableRedraw(True)
    sc.doc.Views.Redraw()

    msg = []
    msg.append("SHP Import 완료")
    msg.append("")
    msg.append("파일: {}".format(os.path.basename(path)))
    msg.append("형식: {}".format(shape_type_name))
    msg.append("DBF 인코딩: {}".format(encoding))
    msg.append("")
    msg.append("Point: {}".format(point_count))
    msg.append("Curve: {}".format(curve_count))
    msg.append("Surface/Brep: {}".format(brep_count))
    msg.append("Failed/Fallback: {}".format(failed_count))
    msg.append("Null Shape: {}".format(null_count))
    msg.append("")
    msg.append("생성 레이어 기준명: {}".format(root_name))
    if use_mapping:
        msg.append("추출 코드: {}".format(extracted_code if extracted_code else "없음"))
        msg.append("치환 이름: {}".format(mapped_name if mapped_name else "매핑 없음 - 원본명 사용"))

    rs.MessageBox("\n".join(msg), 0, "SHP Importer")


if __name__ == "__main__":
    main()
