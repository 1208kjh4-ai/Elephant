# -*- coding: utf-8 -*-
import rhinoscriptsyntax as rs

# ==============================================================================
# 🛠️ [세팅값] 여기에 원하는 단축어와 실행할 매크로/스크립트 경로를 입력하세요.
# ==============================================================================
SHORTCUT_SETTINGS = {
    "Stair": '! _-RunPythonScript "Elephant/Stair.py"',
    "Arrow": '! _-RunPythonScript "Elephant/Arrow.py"',
    "Cross": '! _-RunPythonScript "Elephant/Cross.py"',
    "Tree": '! _-RunPythonScript "Elephant/ArrayTree.py"',
    "AA": '! _-RunPythonScript "Elephant/ArrayBetween"',
    "Parking": '! _-RunPythonScript "Elephant/Parking"',
    "Lane": '! _-RunPythonScript "Elephant/Lane"',
    "Swing": '! _-RunPythonScript "Elephant/Swing"',
    "Sliding": '! _-RunPythonScript "Elephant/Sliding"',
    "Folding": '! _-RunPythonScript "Elephant/Folding"',
    "Spinning": '! _-RunPythonScript "Elephant/Spinning"',
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