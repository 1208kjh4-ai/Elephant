# -*- coding: utf-8 -*-
import Rhino
import Rhino.Geometry as rg
import Rhino.Display as rd
import scriptcontext as sc
import System.Drawing

STICKY_KEY = "ChamferRect_ChamferValue"

def get_chamfered_poly(pts, d):
    if len(pts) < 4: return rg.Polyline(pts + [pts[0]])
    
    new_pts = []
    # 4점 순서: 좌하(0), 우하(1), 우상(2), 좌상(3) 기준
    for i in range(4):
        p_curr = pts[i]
        p_prev = pts[i - 1] # 이전 점 (루프 활용)
        p_next = pts[(i + 1) % 4] # 다음 점
        
        v_prev = rg.Vector3d(p_prev - p_curr)
        v_next = rg.Vector3d(p_next - p_curr)
        
        # d 값이 변의 절반보다 크면 형태가 꼬이므로 제한
        max_d = min(v_prev.Length, v_next.Length) * 0.5
        d_clamped = min(d, max_d)
        
        # 꼭짓점 주변으로 챔퍼점 계산
        p_a = p_curr + (v_prev / v_prev.Length * d_clamped)
        p_b = p_curr + (v_next / v_next.Length * d_clamped)
        
        new_pts.extend([p_a, p_b])
    return rg.Polyline(new_pts + [new_pts[0]])

# 챔퍼 연산 엔진 (8개의 포인트 산출)
def get_chamfered_points(pts, d):
    # pts가 4개가 되었을 때만 계산
    if len(pts) < 4: return pts
    
    new_pts = []
    for i in range(4):
        p_curr = pts[i]
        p_prev = pts[i - 1]
        p_next = pts[(i + 1) % 4]
        
        v_prev = rg.Vector3d(p_prev - p_curr)
        v_next = rg.Vector3d(p_next - p_curr)
        
        # 챔퍼 거리 제한 (변 길이의 절반을 넘지 않게)
        max_d = min(v_prev.Length, v_next.Length) * 0.5
        d_clamped = min(d, max_d)
        
        p_a = p_curr + (v_prev / v_prev.Length * d_clamped)
        p_b = p_curr + (v_next / v_next.Length * d_clamped)
        
        new_pts.extend([p_a, p_b])
    return new_pts

class ChamferConduit(rd.DisplayConduit):
    def __init__(self):
        super(ChamferConduit, self).__init__()
        self.pts = []
        self.curr_pt = None
        self.d = sc.sticky.get(STICKY_KEY, 1.0)
        self.enabled = False

    def DrawOverlay(self, e):
        # 현재까지 찍은 점들과 현재 마우스 커서 위치 결합
        temp_pts = self.pts + ([self.curr_pt] if self.curr_pt else [])
        if len(temp_pts) < 2: return
        
        if len(temp_pts) < 4:
            # 4점 미만일 때는 단순 선(Polyline)으로 프리뷰
            e.Display.DrawPolyline(temp_pts, System.Drawing.Color.Red, 4)
        else:
            # 4점이 다 찍히면 챔퍼된 프리뷰
            poly_pts = get_chamfered_points(temp_pts, self.d)
            e.Display.DrawPolyline(poly_pts + [poly_pts[0]], System.Drawing.Color.Orange, 4)

def main():
    conduit = ChamferConduit()
    conduit.enabled = True
    
    gp = Rhino.Input.Custom.GetPoint()
    gp.SetCommandPrompt("4개의 점을 선택하세요. (값 변경 가능)")
    
    # 명령어 옵션 추가
    op_d = Rhino.Input.Custom.OptionDouble(sc.sticky.get(STICKY_KEY, 1.0))
    gp.AddOptionDouble("Chamfer", op_d)
    
    pts = []
    while len(pts) < 4:
        conduit.d = op_d.CurrentValue
        # 마우스 움직일 때마다 DrawOverlay 실행
        gp.DynamicDraw += lambda sender, e: conduit.DrawOverlay(e)
        
        res = gp.Get()
        
        if res == Rhino.Input.GetResult.Option:
            sc.sticky[STICKY_KEY] = op_d.CurrentValue
            continue
        elif res == Rhino.Input.GetResult.Point:
            pts.append(gp.Point())
            conduit.pts = pts
        else:
            conduit.enabled = False
            return

    # 점 4개 입력 후: Enter 누르기 전까지 여기서 대기하며 수정 가능
    gp.SetCommandPrompt("검토 후 Enter를 누르세요.")
    while True:
        conduit.d = op_d.CurrentValue
        res = gp.Get()
        if res == Rhino.Input.GetResult.Option:
            sc.sticky[STICKY_KEY] = op_d.CurrentValue
            continue
        else:
            break

    conduit.enabled = False
    
    # 최종 생성
    if len(pts) == 4:
        Rhino.RhinoDoc.ActiveDoc.Objects.AddPolyline(get_chamfered_poly(pts, op_d.CurrentValue))
        Rhino.RhinoDoc.ActiveDoc.Views.Redraw()

if __name__ == "__main__":
    main()