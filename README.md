# Elephant Tools

Elephant Tools는 Rhino 7 / Rhino 8에서 사용할 수 있는 건축, 도로, 조경, 구조 관련 Python 스크립트 도구 모음입니다.

이 문서는 Elephant Tools 설치 방법과 기본 사용 흐름을 안내합니다.

## 지원 버전

- Rhino 7
- Rhino 8

## 설치 방법

1. GitHub 저장소의 모든 파일을 ZIP으로 다운로드합니다.

2. Rhino 버전에 맞는 설치 폴더를 만듭니다.

```text
Rhino 7 = %APPDATA%\McNeel\Rhinoceros\7.0\scripts\Elephant
Rhino 8 = %APPDATA%\McNeel\Rhinoceros\8.0\scripts\Elephant
```

3. `Elephant` 폴더가 없다면 새로 생성합니다.

4. 다운로드한 ZIP 파일의 압축을 풀고, 모든 파일과 폴더를 `Elephant` 폴더 안에 넣습니다.

5. 압축 해제 후 폴더 구조는 아래와 같아야 합니다.

```text
%APPDATA%\McNeel\Rhinoceros\X.0\scripts\Elephant                 (O)
%APPDATA%\McNeel\Rhinoceros\X.0\scripts\Elephant-main            (X)
%APPDATA%\McNeel\Rhinoceros\X.0\scripts\Elephant\Elephant-main   (X)
```

`X.0`은 사용하는 Rhino 버전에 따라 `7.0` 또는 `8.0`으로 바꿔 읽으면 됩니다.

## 필수 파일

일부 기능은 Python 파일 외의 보조 파일을 사용합니다. 아래 파일과 폴더가 함께 복사되어 있는지 확인하세요.

- `commands` 폴더
- `system` 폴더
- `ElephantTools.rhc`
- `ElephantToolsR7.rui`
- `Source.3dm`
- `RoadMarkDB.json`
- `shapefile.py`
- `LICENSE-pyshp.txt`
- `icons` 폴더

## 폴더 구조

압축 해제 후 `Elephant` 폴더의 주요 구조는 아래와 같습니다.

```text
Elephant
├─ commands
├─ system
├─ icons
├─ ElephantTools.rhc
├─ ElephantToolsR7.rui
├─ Source.3dm
├─ RoadMarkDB.json
├─ shapefile.py
├─ LICENSE-pyshp.txt
└─ README.md
```

`commands` 폴더에는 실제 실행 도구가 들어 있고, `system` 폴더에는 설치, 업데이트, Alias 등록 관련 스크립트가 들어 있습니다.

## 툴바 설치

Rhino 버전에 맞는 파일을 Rhino 화면 위로 드래그 앤 드롭합니다.

```text
Rhino 7 = ElephantToolsR7.rui
Rhino 8 = ElephantTools.rhc
```

## 명령어 업데이트

툴바에 보이는 `#NEW#` 버튼을 좌클릭하면 Elephant 명령어 Alias가 등록 또는 업데이트됩니다.

`#NEW#` 버튼을 우클릭하면 추가된 명령어 목록을 확인할 수 있습니다.

## 주요 도구

Elephant Tools에는 다음과 같은 도구들이 포함되어 있습니다.

- 문, 창호 관련 도구: `Swing`, `Sliding`, `Folding`, `Spinning`, `CurtainWall`
- 계단 및 건축 요소 도구: `Stair`, `SpiralStair`, `Handrail`, `Parapet`
- 구조 요소 도구: `Truss`, `SpaceTruss`, `3DTruss`, `Hbeam`
- 도로 및 표시 도구: `Arrow`, `Cross`, `Lane`
- 지형 및 SHP 관련 도구: `SHP`, `CreateContour`, `ApplyRoad`, `Building`, `Drop2Srf`
- 기타 도구: `Tree`, `AA`, `MZ`, `DDZ`, `CHP`, `AZ`

## 문제 해결

### 명령어가 실행되지 않을 때

먼저 `Elephant` 폴더가 정확한 위치에 있는지 확인하세요. ZIP 압축을 풀 때 `Elephant-main` 폴더가 한 단계 더 들어가 있으면 명령어가 실행되지 않을 수 있습니다.

또한 `commands`와 `system` 폴더가 `Elephant` 폴더 바로 아래에 있는지 확인하세요.

### SHP 관련 기능이 실행되지 않을 때

`SHP`, `CreateContour`, `Building` 등 일부 기능은 `shapefile.py` 파일이 필요합니다.

SHP 기능이 실행되지 않으면 `shapefile.py` 파일이 `Elephant` 폴더 바로 아래에 있는지 확인하세요.

### 아이콘이나 일부 기능이 보이지 않을 때

`icons` 폴더, `Source.3dm`, `RoadMarkDB.json` 파일이 `Elephant` 폴더 안에 함께 있는지 확인하세요.

## 사용 조건

이 코드는 자유롭게 사용할 수 있습니다.

필요에 따라 수정하거나 배포해도 됩니다.

`shapefile.py`는 pyshp 1.2.12를 포함하며 MIT License를 따릅니다. 자세한 내용은 `LICENSE-pyshp.txt`를 확인하세요.

## 문의

코드가 실행되지 않거나 추가했으면 하는 기능이 있으면 아래 이메일로 연락할 수 있습니다.

```text
1208kjh4@gmail.com
```
