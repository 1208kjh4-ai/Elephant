# -*- coding: utf-8 -*-
import webbrowser

# ==========================================
# [사용자 설정] 공유할 내 GitHub 저장소 링크 입력
# ==========================================
GITHUB_URL = "https://github.com/1208kjh4-ai/Elephant"

def main():
    # 기본 웹 브라우저를 강제로 열어 지정한 GitHub 주소로 이동시킵니다.
    webbrowser.open(GITHUB_URL)

if __name__ == "__main__":
    main()