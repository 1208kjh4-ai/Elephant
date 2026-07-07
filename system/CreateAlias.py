# -*- coding: utf-8 -*-
import rhinoscriptsyntax as rs

# ==============================================================================
# 🛠️ [세팅값] 여기에 원하는 단축어와 실행할 매크로/스크립트 경로를 입력하세요.
# ==============================================================================
SHORTCUT_SETTINGS = {
    "Stair": '! _-RunPythonScript "Elephant/commands/Stair"',
    "Arrow": '! _-RunPythonScript "Elephant/commands/Arrow"',
    "Cross": '! _-RunPythonScript "Elephant/commands/Cross"',
    "Tree": '! _-RunPythonScript "Elephant/commands/ArrayTree"',
    "AA": '! _-RunPythonScript "Elephant/commands/ArrayBetween"',
    "Lane": '! _-RunPythonScript "Elephant/commands/Lane"',
    "Swing": '! _-RunPythonScript "Elephant/commands/Swing"',
    "Sliding": '! _-RunPythonScript "Elephant/commands/Sliding"',
    "Folding": '! _-RunPythonScript "Elephant/commands/Folding"',
    "Spinning": '! _-RunPythonScript "Elephant/commands/Spinning"',
    "Curtainwall": '! _-RunPythonScript "Elephant/commands/CurtainWall"',
    "Handrail": '! _-RunPythonScript "Elephant/commands/Handrail"',
    "SpiralStair": '! _-RunPythonScript "Elephant/commands/SpiralStair"',
    "SpaceTruss": '! _-RunPythonScript "Elephant/commands/SpaceTruss"',
    "3DTruss": '! _-RunPythonScript "Elephant/commands/3DTruss"',
    "Hbeam": '! _-RunPythonScript "Elephant/commands/Hbeam"',
    "Truss": '! _-RunPythonScript "Elephant/commands/Truss"',
    "Drop2Srf": '! _-RunPythonScript "Elephant/commands/Drop2Srf"',
    "MZ": '! _-RunPythonScript "Elephant/commands/MZ"',
    "DDZ": '! _-RunPythonScript "Elephant/commands/DDZ"',
    "Building": '! _-RunPythonScript "Elephant/commands/BakeB"',
    "Parapet": '! _-RunPythonScript "Elephant/commands/Parapet"',
    "CHP": '! _-RunPythonScript "Elephant/commands/CHP"',
    "AZ": '! _-RunPythonScript "Elephant/commands/AZ"',
    "CreateContour": '! _-RunPythonScript "Elephant/commands/CreateContour"',
    "ApplyRoad": '! _-RunPythonScript "Elephant/commands/ApplyRoad"',
    "SHP": '! _-RunPythonScript "Elephant/commands/SHPimport"'
}

# ==============================================================================
# ⚙️ [엔진] 세팅값을 라이노 시스템에 자동 등록하는 로직
# ==============================================================================
def setup_aliases():
    added = []
    updated = []
    skipped = []

    for alias, macro in SHORTCUT_SETTINGS.items():
        # 기존에 등록된 단축어인지 확인
        existing_macro = rs.AliasMacro(alias)
        
        if existing_macro is None:
            # 아예 없는 단축어면 새로 추가
            rs.AddAlias(alias, macro)
            added.append(alias)
        elif existing_macro != macro:
            # 이름은 있는데 매크로가 다르면 덮어쓰기(업데이트)
            rs.AddAlias(alias, macro)
            updated.append(alias)
        else:
            # 이미 똑같이 등록되어 있으면 스킵
            skipped.append(alias)
            
    # 완료 후 사용자에게 팝업으로 결과 보고
    report_msg = "✅ 라이노 단축 명령어(Alias) 세팅이 완료되었습니다!\n\n"
    
    if added:
        report_msg += "➕ [새로 추가됨]: {}\n".format(", ".join(added))
    if updated:
        report_msg += "🔄 [업데이트됨]: {}\n".format(", ".join(updated))
    if skipped and not added and not updated:
        report_msg += "✨ 변경 사항 없음 (모두 이미 최신 상태입니다)."
        
    rs.MessageBox(report_msg, 64, "단축키 자동 등록기")

if __name__ == "__main__":
    setup_aliases()

