# -*- coding: utf-8 -*-
import os
import subprocess
import Rhino
import Rhino.UI

def main():
    # 1. 실행 중인 라이노 버전 체크 (주 버전이 8이 아니면 차단)
    rhino_version = Rhino.RhinoApp.ExeVersion
    if rhino_version != 8:
        Rhino.UI.Dialogs.ShowMessageBox(
            "라이노 8.0 버전이 필요합니다.\n(현재 버전: v{})".format(rhino_version), 
            "버전 불일치"
        )
        return

    # 2. 사용자의 윈도우 Roaming AppData 기본 경로 추적
    appdata_roaming = os.environ.get('APPDATA')
    if not appdata_roaming:
        Rhino.UI.Dialogs.ShowMessageBox("AppData 경로를 찾을 수 없습니다.", "오류")
        return

    # 3. Elephant 최종 타깃 폴더 경로 조립 (라이노 8 경로 고정)
    target_dir = os.path.join(appdata_roaming, "McNeel", "Rhinoceros", "8.0", "Scripts", "Elephant")

    # 4. 폴더가 존재하지 않는 경우 자동 생성
    if not os.path.exists(target_dir):
        try:
            os.makedirs(target_dir)
        except Exception as e:
            Rhino.UI.Dialogs.ShowMessageBox("폴더 생성 중 오류 발생:\n{}".format(str(e)), "오류")
            return

    # 5. 윈도우 파일 탐색기로 해당 경로 강제 팝업
    try:
        subprocess.Popen('explorer "{}"'.format(target_dir))
    except Exception as e:
        Rhino.UI.Dialogs.ShowMessageBox("탐색기를 열 수 없습니다:\n{}".format(str(e)), "오류")

if __name__ == "__main__":
    main()