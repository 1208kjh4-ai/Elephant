# Auditorium Generator 현재 개발 상태 및 인수인계

> 최종 갱신: 2026-07-31 (천장 구간·발코니 Offset·Radial 프리뷰·좌석 Bake 보완)  
> 대상 환경: Rhino 8 / Python 3 / RhinoCommon / Eto.Forms  
> 패키지: ElephantTools 1.0.3  
> Rhino 명령: `Auditorium`

---

## 1. 가장 중요한 현재 경로

현재 실제 실행 기준 파일은 예전 `TTest.py`가 아니다.

```text
C:\Users\실습\AppData\Roaming\McNeel\Rhinoceros
\packages\8.0\ElephantTools\1.0.3\content\commands\Auditorium.py
```

실제 기능은 다음 패키지에 모듈로 분리되어 있다.

```text
...\content\commands\auditorium_generator\
```

`Auditorium.py`는 실행 진입점이자 호환용 import 표면이다. 명령을 실행할
때 `auditorium_generator` 모듈을 다시 불러오므로, 설정창을 닫고
`Auditorium` 명령을 다시 실행하면 수정 코드가 로드된다.

다음 파일은 이전 단일 파일 버전이므로 현재 수정의 기준으로 사용하지 않는다.

```text
...\content\commands\TTest.py
```

작업 중 사용한 검증용 복사본은 다음 경로에 있다.

```text
C:\Users\실습\AppData\Roaming\McNeel\Rhinoceros\8.0\scripts
\_auditorium_1_0_3_work\content\commands
```

실제 배포 상태를 확인할 때는 반드시 `packages` 아래의 1.0.3 파일을
기준으로 판단한다.

---

## 2. 궁극적인 개발 목표

공연장 좌석 배치 도구를 다음 범위까지 발전시키는 것이 목표다.

1. 공연장 중앙 종단면과 시야 계산
2. 직사각형 및 방사형 객석 평면 배치
3. 일반석과 최대 2개 층 발코니석
4. 무대, 객석, 난간, 천장 등의 3D 공간 및 면
5. 외부 3DM 좌석 모듈을 이용한 실제 3D 좌석 배치
6. 추후 사용자 정의 경계선을 이용한 비정형 좌석 배치

현재는 중앙 종단면 계산, 발코니, 무대 공간, 3D 좌석, 면 생성,
치수 보간, 직사각형 평면 및 초기 Radial 평면까지 연결된 상태다.

---

## 3. 전체 실행 흐름

```text
관객에서 무대를 볼 때 왼쪽→오른쪽 순서로 기준점 2개 입력
  → 두 점의 수평 기준선 및 객석 최저 바닥 Datum 분석
  → 메인 설정창
  → PW·PH 및 Proscenium/Open·Podium 무대 유형 설정
  → Rectangular/Radial 평면 기준 계산
  → 일반석 시야 및 단면 계산
  → 선택적 단면 총높이 보간
  → 발코니 1 계산 및 보간
  → 발코니 2 계산 및 보간
  → 열별 좌석 블록 및 총 좌석 수 계산
  → Curve/Point/Label/Mesh/Brep 프리뷰 생성
  → OK를 누르면 Bake
```

핵심 통합 함수는 다음과 같다.

```python
build_preview_geometry(...)
```

이 함수는 문서에 즉시 객체를 추가하지 않고 프리뷰 및 Bake용 데이터를
구성한다.

---

## 4. 좌표계와 기준점

### 4.1 직사각형 모드

- 사용자가 찍은 수평선의 중간점과 Z가 객석 최저 바닥 Datum이다.
- 첫 점은 관객 시점 왼쪽, 둘째 점은 관객 시점 오른쪽이다.
- 첫 점→둘째 점은 `audience_view_right_direction`이다.
- 객석 방향은 `audience_view_right × World Z`로 계산하며 무대에서
  객석을 향한다.
- 객석 방향이 중앙 종단면의 로컬 +X 방향이다.
- 객석 첫 플랫폼의 실제 높이는 입력 기준선 Z와 정확히 일치한다.
- 무대 바닥은 객석 Datum에서 `stage_height`만큼 올라간다.
- 내부 단면 계산은 무대 바닥을 로컬 Z=0으로 유지하고, 첫 플랫폼을
  `-stage_height`로 계산한 뒤 실제 무대 원점을 위로 이동한다.
- `first_row_distance`는 기준점에서 첫 객석 플랫폼 시작점까지의 거리다.

좌우는 항상 **객석에서 무대를 바라보는 기준**이다. `Flip Direction`을
누르면 객석 방향과 관객 시점 오른쪽이 함께 반전되며, RightStage와
LeftStage 파라미터 자체를 서로 교환하지 않는다.

### 4.2 Radial 모드에서 반드시 구분할 점

Radial에는 서로 다른 두 점이 존재한다.

- 원의 중심점 `Center`: 원호 계산과 회전면 생성축으로만 사용
- 원호의 중간점 `Mid`: 시각선 기준점과 중앙 종단면의 실제 기준점

시각선 기준점은 원의 중심점이 아니라 **원호의 중간점**이다.

이 구분은 한 번 잘못 구현되었다가 2026-07-30에 수정되었다. 향후
리팩터링할 때 다시 혼동하지 않아야 한다.

### 4.3 PW·PH와 무대 유형

- PW 기본값은 새로 입력한 두 점 기준선의 길이이며 매 명령마다 갱신된다.
- PW는 텍스트박스에서 수정할 수 있다.
- PH 기본값은 6,000 mm이고 최솟값은 3,000 mm다.
- PH는 Open/Podium에서도 상부 시야 기준, 발코니 하부 한계선,
  객석 천장 `2 × PH` 계산에 계속 사용한다.
- Proscenium 모드에서는 PW×PH 가상 개구부 프레임, 플라이타워,
  그리드, 좌우 2 m 공간, 좌우·후방무대를 생성한다.
- Open/Podium 모드에서는 주무대 바닥, 에이프런, 피트, 객석 전이부만
  유지하고 프로시니엄 수직 프레임, 플라이타워, 그리드, 좌우 2 m 공간,
  좌우·후방무대를 생성하지 않는다.
- 하부무대는 무대 유형과 별개의 옵션이므로 Open/Podium에서도 사용할
  수 있다.
- PW/PH 공식 기본값과 일치하는 무대 치수만 PW/PH 변경에 따라 자동
  갱신하며, 사용자가 직접 바꾼 개별 치수는 보존한다.

---

## 5. Radial 평면 계산

### 5.1 입력

메인 창의 입력값:

```text
Plan radius (0 = rectangular, min. PW / 2)
```

- `R = 0`: 기존 직사각형 방식
- `R >= PW / 2`: Radial 방식
- `0 < R < PW / 2`: 자동으로 `0`으로 정규화하여 직사각형 방식

### 5.2 기준 원호

편집 가능한 PW의 가상 개구부 하단 양 끝점이 기준 원호를 통과한다.

```text
W = 개구부 폭 PW
h = W / 2
R = 사용자 입력 반지름
d = sqrt(R² - h²)
half_angle = asin(h / R)
sagitta = R - d
```

기호:

- `M`: 입력 기준선의 평면 중심에 놓인 가상 개구부 하단 중간점
- `D`: 객석 방향 단위벡터
- `C`: 원의 중심
- `Q`: 기준 원호 중간점

```text
C = M - D × d
Q = C + D × R
```

따라서 `Q`는 개구부의 직선 중심에서 객석 방향으로 `sagitta`만큼
돌출된 원호 중간점이다.

### 5.3 단면과 시각선

- 하부 시각선 기준점: `Q + stage_sight_point_z`
- 상부 시각선 기준점: `Q + PH`
- 중앙 종단면의 로컬 X = 0: `Q`
- 첫 플랫폼 시작점: `Q + D × first_row_distance`
- 무대 돌출값과 오케스트라 피트도 `Q`에서 시작하는 단면 기준으로 계산

반지름은 평면의 펼침 정도를 바꾸지만, 같은 단면 입력에서 객석의
로컬 X/Z 시야 해는 바꾸지 않는다. 그러므로 현재
`plan_layout_radius`는 단면 높이 보간을 무효화하는 solver signature에
포함되지 않는다.

### 5.4 각 객석 열

단면 계산에서 얻은 열 위치를 `x_i`라고 할 때 실제 원호 반지름은 다음과
같다.

```text
row_radius_i = R + x_i
```

각 열은 기준 원호와 같은 각도 범위에서 동심원호로 생성된다.

```text
included_angle = 2 × half_angle
row_arc_length = 2 × half_angle × row_radius_i
```

3D 좌석은 열 원호 위에 놓이며, 각 좌석의 로컬 X축은 해당 점의 원호
접선 방향, 로컬 Y축은 반지름 바깥 방향을 따른다.

### 5.5 Radial 면

중앙 종단면의 다음 커브는 원의 중심축을 기준으로 원호 각도만큼
회전되어 Brep 면이 된다.

- 일반석 바닥과 단
- 통로 및 통로 계단 단면
- 발코니 바닥
- 발코니 난간 전면과 상부
- 무대 돌출 및 오케스트라 피트 전이부
- 객석 천장
- 객석 후벽

프로시니엄 무대의 평면과 공간은 여전히 선택한 개구부의 실제 하단선
중간점 `M`을 기준으로 생성한다.

---

## 6. 좌석 블록 입력과 `a` 자동 배열

### 6.1 고정 좌석 블록

기존 정수 입력은 그대로 지원한다.

```text
8,16,8
```

의미:

- 좌석 블록 3개
- 좌석 수 8 / 16 / 8
- 블록 사이 세로 통로 2개
- 통로 폭은 `Longitudinal aisle width`

### 6.2 자동 블록 `a`

Radial 모드에서 좌석 블록에 `a` 또는 `A`를 입력할 수 있다.

```text
8,a,8
a,8,a
a,a,a,a,a
```

동작:

- 정수는 고정 좌석 수다.
- `a`는 각 열에서 사용 가능한 원호 길이에 맞추어 자동 계산한다.
- 대문자 `A`는 소문자 `a`로 정규화한다.
- 뒤쪽 열은 원호 길이가 길어지므로 자동 좌석 수가 증가할 수 있다.
- 일반석과 유효한 모든 발코니 열에 같은 규칙을 적용한다.
- 총 좌석 수 표시와 3D 좌석/팔걸이 배치에도 열별 결과를 사용한다.

### 6.3 자동 좌석 수 계산

한 열에서:

```text
B = 전체 좌석 블록 수
K = a 블록 수
F = 정수 블록의 고정 좌석 수 합계
S = 좌우 side_floor_margin
A = longitudinal_aisle_width
P = seat_module_width
L = 해당 열의 전체 원호 길이
```

통로와 좌우 여백을 제외한다.

```text
usable_width = L - 2S - (B - 1)A
capacity = floor(usable_width / P)
```

자동 블록 하나당 좌석 수:

```text
auto_seats = floor((capacity - F) / K)
```

모든 `a` 블록에는 같은 좌석 수를 넣는다. 나누어떨어지지 않는 잔여
폭은 좌석을 한쪽에 더 넣지 않고 전체 좌석 조합의 좌우 여유 폭으로
남긴다. 따라서 `a,8,a`와 같이 대칭 입력은 좌우 자동 블록의 좌석 수도
동일하다.

### 6.4 예시

```text
8,a,8
```

- 양쪽 8석 고정
- 중앙 블록이 나머지 폭을 사용

```text
a,8,a
```

- 중앙 8석 고정
- 좌우 자동 블록을 같은 좌석 수로 생성

```text
a,a,a,a,a
```

- 좌석 블록 5개
- 블록 사이 세로 통로 4개
- 다섯 블록에 같은 자동 좌석 수 적용

### 6.5 현재 제한

- `a`는 유효한 Radial 모드에서만 사용할 수 있다.
- 반지름이 `0`이거나 `PW/2`보다 작으면 명시적인 오류를 표시한다.
- 직사각형 평면은 외부 기준 폭이 없고 좌석 조합 자체가 폭을 결정하므로
  현재 `a`를 지원하지 않는다.
- 한 열의 좌석 수 상한은 500석이다.
- 모든 자동 블록에 최소 1석도 들어가지 못하면 오류를 표시한다.
- 3D 좌석 프리뷰 전체 상한은 10,000석이다.

핵심 함수:

```python
seat_blocks_have_auto(...)
resolve_row_seat_block_counts(...)
calculate_3d_seat_placements(...)
calculate_total_3d_seat_count(...)
```

---

## 7. 중앙 종단면과 시야 계산

핵심 함수:

```python
calculate_section(params)
```

기본 흐름:

1. 첫 객석 플랫폼 및 첫 눈 위치 계산
2. 앞 열 눈 위치와 시야 여유를 만족하도록 다음 열 높이 계산
3. 횡단 통로가 있으면 통로 폭과 계단 추가 길이를 X에 반영
4. 실제 시야 여유, 경사, 천장 충돌 검증
5. 각 열의 바닥, 좌석, 눈 위치, 시각선 생성

현재 초기 단 높이는 계산된 부동소수점 값을 유지한다. 예전처럼 최초
계산 단계에서 무조건 정수 mm로 올림하지 않는다. 건축 치수 정리는
별도의 단면 총높이 보간 기능에서 수행한다.

주요 기본값:

| 항목 | 기본값 |
|---|---:|
| Stage height | 1,100 mm |
| Reference arc/stage to first platform | 7,000 mm |
| Row pitch | 1,100 mm |
| Stage apron projection | 1,200 mm |
| Orchestra pit depth | 0 mm |
| Stage sight target height | 50 mm |
| Chair sight point Z | 1,123.991949 mm |
| Sightline clearance | 113 mm |
| Maximum slope | 1/12 |
| Plan radius | 0 |

---

## 8. 열 그룹, 횡단 통로, 통로 계단

객석 열은 쉼표로 그룹화할 수 있다.

```text
12,12,12
```

쉼표 위치마다 횡단 통로를 넣는다.

통로 계단 기본 규칙:

```text
목표 계단 높이 = 170 mm
기본 디딤판 깊이 = 300 mm
추가 단 수 = round(전체 높이차 / 170) - 1
실제 단 높이 = 전체 높이차 / (추가 단 수 + 1)
```

추가 단 수만큼 다음 객석 열을 뒤로 이동시키고, 변경된 X 위치에서
시야 높이를 다시 계산한다.

마지막 일반석과 각 발코니의 마지막 열 뒤에는 후방 횡단 통로가 생성된다.

---

## 9. 무대 및 프로시니엄 공간

메인 창의 `프로시니엄 수정` 버튼에서 별도 설정창을 연다.

기본 계산:

```text
주무대 폭   = PW + 8,000
주무대 깊이 = PW × 1.2
```

구성:

- 주무대
- 오른무대
- 왼무대
- 뒷무대
- 하부무대

오른무대, 왼무대, 뒷무대, 하부무대는 기본 On이다.

주무대와 좌우무대 사이에는 좌우 각각 2,000 mm의 고정 여유 공간이
항상 존재한다. 좌우무대가 꺼져도 이 여유 공간은 유지한다.

PH 기반 초기 단면:

```text
Flytower 상단      = PH × 3 + 2,000
Flytower grid      = PH × 3
좌우/후방무대 상단 = PH + 2,000
좌우/후방무대 grid = PH
하부무대 최하단    = -(PH + 2,000)
하부 설비 바닥     = -PH
객석 천장          = PH × 2
```

프로시니엄 설정창에서 2D 중앙 종단면 또는 3D 공간 커브 프리뷰를
선택할 수 있다. 수치와 On/Off 변경은 실시간 프리뷰에 반영된다.

---

## 10. 무대와 객석 사이

- 무대 돌출 기본값: 1,200 mm
- 오케스트라 피트 깊이: 객석 바닥 기준 하향 깊이
- 피트 깊이가 0이면 피트 없음
- 첫 플랫폼 시작 거리 기본값: 7,000 mm

Radial 모드에서는 위 거리들이 원의 중심이 아니라 기준 원호의
중간점 `Q`를 기준으로 한다.

---

## 11. 발코니석

최대 2개 층을 지원한다.

각 층의 설정:

- On/Off
- 좌석 열 수
- 열 간격
- 마지막 플랫폼 높이
- 난간 `t`, `w`, `h`

발코니 높이 입력은 일반석 마지막 플랫폼 높이를 0으로 본 상대 높이다.
내부 계산에서는 절대 Z로 변환한다.

발코니 생성:

- 입력한 마지막 플랫폼 높이에서 앞쪽으로 역산
- 가능한 최대 좌석 열 수 계산
- 최대 경사각 35도 검증
- 아래층 시야 한계와 위층 천장 충돌 검증
- 첫 열 시각선과 난간 충돌 검증
- 마지막 열 뒤쪽 후방 통로 생성
- 1층 발코니가 유효해야 2층 발코니 생성

난간은 단면 커브뿐 아니라 객석 폭 또는 Radial 각도 전체로 연장된
면으로 생성된다.

---

## 12. 시각선 표시

- 모든 열의 하부 기준점 시각선
- 첫 열과 마지막 열의 상·하 기준 시각선
- 첫 열과 마지막 열의 강조 색상은 주황색
- 상부 기준점은 개구부 상단 중심 높이
- 하부 기준점 높이는 사용자가 입력

Radial에서는 상·하 기준점의 평면 위치가 기준 원호 중간점이다.

---

## 13. 단면 치수와 총높이 보간

프리뷰 전용 치수:

- 각 단의 실제 높이
- 객석과 발코니의 외곽 총합 높이 치수
- 치수 및 텍스트는 Bake하지 않음

별도 창:

```text
Section Dimension Interpolation
```

지원 영역:

- Stalls
- Balcony 1
- Balcony 2

일반석은 첫 플랫폼 높이를 고정하고 뒤쪽으로 비례 보간한다.

```text
z_new[i] = z_first
           + (z_old[i] - z_first)
           × target_rise / current_rise
```

발코니는 사용자가 지정한 마지막 플랫폼 높이를 고정하고 앞쪽으로
비례 보간한다.

```text
z_new[i] = z_last
           - (z_last - z_old[i])
           × target_rise / current_rise
```

10 mm 내림, 반올림, 올림 선택을 제공한다. 보간 후 실제 시야, 경사,
난간, 천장 조건을 다시 검증한다.

### 보간 무효화 규칙

다음과 같이 실제 X/Z 시야 해를 바꾸는 입력은 관련 보간값을 무효화한다.

- 무대 높이
- 첫 플랫폼 거리
- 열 간격
- 시각선 상·하 기준 높이
- 시야 여유
- 열 그룹
- 횡단 통로 폭
- 통로 계단 디딤판 깊이
- 바닥 방식
- 발코니 열 수, 열 간격, 마지막 플랫폼 높이

다음 값은 단면 시야 해를 바꾸지 않으므로 보간값을 유지한다.

- 좌석 폭
- 좌석 블록 조합 및 `a`
- 세로 통로 폭
- 좌우 바닥 여백
- 오케스트라 피트 깊이
- 무대 돌출 길이
- 발코니 난간 `t`, `w`, `h`
- 프리뷰 표시 옵션
- Radial 반지름

---

## 14. 3D 좌석 모듈

소스 파일:

```text
...\ElephantTools\1.0.3\content\AuditoriumSeat.3dm
```

인식 이름:

- 의자: `TT_ChairBody`
- 팔걸이: `TT_Armrest`

기준 치수:

- 기준 의자 폭: 400 mm
- 팔걸이 폭: 80 mm

배치 규칙:

- Bounding Box가 아니라 원본 블록의 `(0,0,0)`을 삽입 기준으로 사용
- 소스에 저장된 Z 이격 유지
- 의자 본체만 로컬 X 방향으로 폭 조절
- 팔걸이 폭은 변경하지 않음
- 인접 좌석은 팔걸이를 공유
- 일반석과 모든 유효 발코니에 배치
- 기본 3D 좌석 프리뷰는 Off
- 총 좌석 수는 프리뷰 On/Off와 관계없이 표시
- 3D 좌석 프리뷰가 On이면 중앙 종단면의 2D 의자 Curve는 생성하지 않음
- 총 좌석 수가 1,000석 이하이면 음영 Mesh로 프리뷰
- 총 좌석 수가 1,000석을 초과하면 의자와 팔걸이를 Wire Line으로 프리뷰
- Wire Line 모드에서도 OK를 누르면 기존 3D 블록 Instance를 정상 Bake

Radial에서는 각 좌석이 원호의 접선 방향을 향한다.

---

## 15. 면 생성

`Show floor surfaces`가 켜져 있을 때 프리뷰 및 Bake용 Brep을 생성한다.

직사각형:

- 중앙 단면 커브를 객석 폭 방향으로 Extrude

Radial:

- 중앙 단면 커브를 원의 중심축 주위로 기준 원호 각도만큼 Revolve

생성 대상:

- 주무대 및 보조무대 바닥
- 무대 상부 및 하부 공간 외피
- 무대 돌출과 피트
- 일반석 바닥, 단, 통로, 통로 계단
- 발코니 바닥과 난간
- 객석 천장과 후벽

---

## 16. 주요 모듈

| 파일 | 역할 |
|---|---|
| `Auditorium.py` | 명령 진입점, hot reload, 호환 import |
| `command_runtime.py` | 개구부 선택, 대화상자 실행, Bake 호출 |
| `main_dialog.py` | 메인 Eto UI, 입력 파싱, 프리뷰 갱신 |
| `preview_geometry.py` | 전체 계산 및 프리뷰 형상 통합 |
| `radial_layout.py` | 반지름 정규화, Center/Mid, 원호, 회전면 |
| `calculations/sections.py` | 일반석/발코니 시야, 경사, 보간 |
| `calculations/seating.py` | 고정 및 `a` 좌석 블록, 총 좌석 수 |
| `calculations/stage.py` | 프로시니엄 기본값과 PH 기반 높이 |
| `stage_preview_geometry.py` | 무대 평면, 공간, 단면, 피트 |
| `balcony_preview_geometry.py` | 발코니 커브 및 좌석 형상 |
| `seat_preview_geometry.py` | 3D 의자와 팔걸이 Transform |
| `seat_source.py` | `AuditoriumSeat.3dm` 로딩 |
| `floor_surface_geometry.py` | 직사각형 Extrude 및 Radial Revolve |
| `section_preview_annotations.py` | 단 높이 및 외곽 총합 치수 |
| `section_result_dialogs.py` | 계산 결과와 높이 보간 팝업 |
| `document_baking.py` | Curve/Point/Brep/Instance Bake |
| `preview_conduit.py` | Rhino DisplayConduit 프리뷰 |

---

## 17. `build_preview_geometry()` 주요 반환값

```text
preview_curves
preview_points
preview_meshes
preview_wire_meshes
preview_labels
bake_curves
bake_points
bake_breps
bake_instances
calculation
balcony_calculations
seat_3d_calculations
floor_surface_calculation
plan_layout
total_seat_count
seat_3d_preview_mode
stage_section_dimensions
applied_section_rise_overrides
```

`preview_labels`에 있는 단 높이와 외곽 치수 텍스트는 Bake 대상이 아니다.

---

## 18. 최근 Radial 및 `a` 수정 파일

Radial 추가 및 원호 Mid 기준 수정:

```text
Auditorium.py
auditorium_generator/radial_layout.py
auditorium_generator/main_dialog.py
auditorium_generator/preview_geometry.py
auditorium_generator/seat_preview_geometry.py
auditorium_generator/floor_surface_geometry.py
auditorium_generator/stage_preview_geometry.py
auditorium_generator/calculations/sections.py
```

자동 좌석 `a` 추가:

```text
Auditorium.py
auditorium_generator/calculations/seating.py
auditorium_generator/main_dialog.py
auditorium_generator/preview_geometry.py
auditorium_generator/seat_preview_geometry.py
auditorium_generator/floor_surface_geometry.py
```

---

## 19. 완료된 검증

2026-07-30 실제 Rhino 8 런타임에서 확인:

- 반지름 0의 기존 직사각형 프리뷰
- 유효 반지름의 기준 원호
- 원호 양 끝점과 개구부 하단 양 끝점 일치
- 원의 Center와 원호 Mid 분리
- 시각선 기준점이 원호 Mid에 위치
- 반지름 변경 시 단면 X/Z 해 유지
- 각 열의 실제 반지름이 `R + x_i`
- Radial 회전 바닥면 생성
- 좌석 원호 접선 Transform
- `8,a,8` 파싱과 중앙 자동 좌석
- `a,8,a` 좌우 대칭 자동 좌석
- 대문자 `A` 정규화
- 뒤 열의 자동 좌석 수 증가
- 자동 좌석 총합 계산
- `a`를 사용한 3D 배치 데이터
- `a`의 직사각형 모드 차단
- 고정 블록 직사각형 모드 회귀 검사
- Auditorium 관련 Python 파일 32개의 문법 검사

검증 과정에서 생성한 임시 테스트 파일은 제거했다.

2026-07-31 실제 Rhino 8 호스트에서 비베이크 스모크 테스트:

- 두 점 기준선의 관객 시점 좌우 및 기본 객석 방향
- Flip 후 객석 방향과 관객 시점 오른쪽 동시 반전
- 기준선 Z와 첫 객석 플랫폼 실제 Z 일치
- 무대 바닥이 객석 Datum에서 `stage_height`만큼 상승
- PW 10,000 / PH 6,000의 계산 기본값
- PH 3,000 mm 최소값과 유한수 검증
- Proscenium 기본 6공간
- Open/Podium의 MainStage 단일 평면과 억제 대상 미생성
- PW×PH 가상 개구부 프레임의 Proscenium 전용 생성
- Radial 원호 양 끝, Mid, Center 및 관객 시점 좌우 부호
- 메인 Eto Dialog 초기 프리뷰
- Stage Space Settings의 유형별 활성/비활성 상태
- Auditorium 관련 수정 모듈 전체 문법 검사

---

## 20. 다음 개발 시 권장 과제

### 20.1 2D 평면 좌석 심벌

현재 `a`는 총 좌석 수와 3D 좌석 배치에 연결되어 있다. 개별 좌석의
2D 평면 심벌은 아직 별도 기능으로 완성되지 않았다.

다음 단계:

1. 의자와 팔걸이의 경량 2D 심벌 정의
2. 직사각형에서는 평행 배치
3. Radial에서는 원호 접선 방향 배치
4. 프리뷰와 Bake 레이어/이름 분리

### 20.2 Radial 세로 통로의 명확한 평면 표현

현재 좌석 블록 사이 간격으로 통로 폭을 확보한다. 다음 단계에서는
통로 경계선과 바닥 영역을 실제 방사형 평면 커브/면으로 명확하게
보여주는 것이 좋다.

### 20.3 사용자 정의 비정형 경계

논의한 아이디어:

- 첫 열과 마지막 열의 반쪽 경계에 사용자가 여러 개의 가이드 Line 생성
- 공연장 중앙축을 기준으로 반대쪽 대칭
- 각 열에서 가이드 Line과의 교점으로 블록 경계 계산
- 정수 블록과 `a` 블록을 혼합하여 남은 폭 자동 배치

이 기능은 Radial보다 입력 데이터와 교차 검증이 복잡하므로 별도 단계로
진행하는 것이 안전하다.

### 20.4 `a` 분배 방식 확장

현재 여러 `a`는 모두 같은 좌석 수를 가진다. 향후 필요하면 다음 선택지를
추가할 수 있다.

- 잔여 1석을 중앙 블록부터 배분
- 좌우 대칭을 우선하고 중앙에만 잔여 배분
- 블록별 가중치 입력
- 최소/최대 좌석 수 지정

### 20.5 사용자 시각 검증

계산 및 Rhino 런타임 스모크 테스트는 통과했지만, 실제 공연장 크기에서
다음 항목은 사용자 눈으로 추가 확인하는 것이 좋다.

- 기준 원호의 돌출 방향
- 무대 돌출과 기준 원호의 관계
- Radial 첫 열과 프로시니엄 개구부 사이 형태
- 발코니 회전면과 아래층 시야 한계
- 5개 이상 자동 블록에서 통로가 의도한 방향으로 보이는지

---

## 21. 개발 주의사항

- 실제 수정 기준은 패키지의 모듈 파일이며 `TTest.py`가 아니다.
- UI 입력 단위는 mm이며 Rhino 문서 단위 변환은 `unit_scale_from_mm()`을
  사용한다.
- Radial에서 원의 중심과 원호 중간점을 혼동하지 않는다.
- 시각선 기준은 원호 중간점이다.
- 회전면 축은 원의 중심이다.
- 좌석 열 반지름은 `R + 단면 x`다.
- `a` 계산 시 좌우 여백과 모든 블록 사이 통로를 먼저 제외한다.
- 좌석 원본은 Bounding Box가 아니라 블록 원점으로 배치한다.
- 팔걸이 폭은 스케일하지 않는다.
- 단 높이 및 외곽 치수 라벨은 Bake하지 않는다.
- 사용자 파일의 관련 없는 변경을 덮어쓰지 않는다.
- 실제 패키지 반영 전 작업 복사본에서 문법 및 Rhino 런타임 검증을
  수행하는 흐름을 유지한다.

---

## 22. 빠른 재개 체크리스트

1. `packages\...\1.0.3\content\commands\Auditorium.py`가 실행 기준인지 확인
2. `auditorium_generator` 모듈의 현재 파일을 확인
3. Rhino의 기존 Auditorium 설정창을 닫음
4. `Auditorium` 명령을 다시 실행
5. 관객 시점 왼쪽→오른쪽 순서로 기준선 두 점 입력
6. 첫 객석 플랫폼 Z가 입력 기준선 Z와 일치하는지 확인
7. Proscenium/Open·Podium 전환 및 PW×PH 프레임 확인
8. 직사각형 `8,16,8` 회귀 확인
9. Radial 반지름을 `PW/2` 이상으로 설정
10. 시각선 기준점이 원호 Mid인지 확인
11. `8,a,8`, `a,8,a`, `a,a,a,a,a` 확인
12. 총 좌석 수와 3D 좌석 배치 확인
13. 면 프리뷰를 켜서 Radial 회전면 확인

---

## 23. 2026-07-31 추가 구현 기록

### 23.1 최상층 후방 플랫폼~객석 천장 높이 제어

기존 `Section Dimension Interpolation` 기능을
`Section Dimension Control`로 확장했다.

팝업에서 다음 구간의 총높이를 함께 수정할 수 있다.

- 일반 객석 전체 상승 높이
- Balcony 1 전체 상승 높이
- Balcony 2 전체 상승 높이
- 최상층의 마지막 플랫폼에서 객석 천장까지의 수직 높이

천장 기준층은 활성화된 객석층에 따라 자동으로 선택한다.

```text
Balcony 2가 유효함 → Balcony 2 마지막 플랫폼
Balcony 1만 유효함 → Balcony 1 마지막 플랫폼
발코니가 없음      → Stalls 마지막 플랫폼
```

천장 구간 계산:

```text
reference_z = 최상층 마지막 플랫폼 Z
minimum_clear_height = max(0, PH - reference_z)
actual_clear_height = max(사용자 입력 높이, minimum_clear_height)
auditorium_ceiling_z = reference_z + actual_clear_height
```

따라서 사용자가 입력한 구간 높이로 계산한 천장이 개구부 상단보다
낮아지면, 천장 Z를 개구부 상단 `PH`까지만 낮춘다.

사용자 Override가 없으면 기존 `PH × 2` 천장 공식을 기본값으로
사용하되, 유효한 기준 플랫폼과 개구부 상단보다 낮아지지 않도록
정규화한다.

최종 천장 Z를 계산한 뒤 다음 항목을 다시 검증하거나 갱신한다.

- 일반 객석 의자 상단과 천장의 충돌
- Balcony 1·2 의자 상단과 천장의 충돌
- 중앙 종단면 천장선
- 객석 후벽
- 외곽 구간 치수
- 직사각형 천장·후벽 면
- Radial 천장·후벽 회전면
- `Calculated Result`의 천장 높이와 경고

천장 높이 Override는 좌석 시각선 상승 높이 Override와 분리했다.
의자 폭, 좌석 블록, 통로 폭 등 시각선 해를 바꾸지 않는 입력이
변경되어도 천장 입력값은 유지된다.

현재 정책상 개구부 상단 조건으로 보정된 천장 간격은 보정 후의 실제
값으로 저장된다. 이후 PH가 다시 낮아지더라도 최초의 더 작은 요청값으로
자동 복귀하지 않는다.

핵심 함수:

```python
calculate_auditorium_ceiling(...)
add_stalls_ceiling_validation(...)
add_balcony_ceiling_validation(...)
```

### 23.2 Balcony 1·2 종방향 Offset

각 발코니 설정창에 다음 입력을 추가했다.

```text
Offset from stalls rear (mm, + rear / - stage)
```

기준은 일반 객석 마지막 열의 X 위치다.

```text
balcony_rear_row_x
    = stalls_last_row_x + balcony_longitudinal_offset
```

- 양수: 무대에서 멀어지는 후방 방향
- 음수: 무대 쪽으로 이동하는 전방 방향
- `0`: 기존처럼 일반 객석 마지막 열과 같은 후방 기준

Balcony 1과 Balcony 2는 모두 같은 일반 객석 후방 Datum을 사용하며,
각 Offset은 서로 독립적이다. Balcony 2의 하부 시야 한계 검증은
여전히 Balcony 1을 하부층으로 사용한다.

Offset은 완성된 형상을 사후 이동시키는 값이 아니다. 발코니 시각선
계산 전에 마지막 열 X를 바꾸므로 다음 결과가 모두 새 위치에서
재계산된다.

- 발코니 각 열의 X/Z
- 시각선과 실제 시야 여유
- 경사각
- 난간 위치와 첫 열 시야 충돌
- 아래층 시야 한계
- 가능한 최대 열 수
- 2D 단면 의자와 바닥선
- 직사각형 및 Radial 3D 좌석
- 발코니 바닥·난간 면
- Bake용 Curve, Brep, Instance

Offset은 발코니 solver signature에 포함된다.

```text
Balcony 1 Offset 변경 → Balcony 1·2 상승 높이 Override 무효화
Balcony 2 Offset 변경 → Balcony 2 상승 높이 Override 무효화
천장 높이 Override    → 유지
```

극단적인 Offset에 대한 방어 규칙도 추가했다.

- 가능한 발코니 최대 열 수 상한: 500열
- 전방 Offset으로 한 열도 들어갈 수 없으면 최대 열 수 `0`
- 최대 열 후보 판정에서 전방 한계 위반도 검사
- NaN과 무한대 Offset 입력 거부

### 23.3 후벽, 후방 통로 및 바닥 마감 구간

발코니가 일반 객석보다 뒤로 이동할 수 있으므로 전역 후벽 X는 다음과
같이 계산한다.

```text
rear_wall_x = max(
    Stalls 마지막 열 + 후방 통로 폭,
    Balcony 1 마지막 열 + 후방 통로 폭,
    Balcony 2 마지막 열 + 후방 통로 폭
)
```

초기 구현에서는 후방으로 이동한 발코니 Offset만큼 일반 객석의
`RearCrossAisle`도 길어지는 문제가 있었다. 현재는 다음처럼 분리한다.

```text
RearCrossAisle
    = Stalls 마지막 열부터 사용자가 입력한 후방 통로 폭까지만 생성

AuditoriumRearFloorClosure
    = Stalls 후방 통로 끝에서 전역 후벽까지의 별도 바닥 마감 구간
```

`AuditoriumRearFloorClosure`는 프리뷰 Curve뿐 아니라 면 프리뷰가
켜졌을 때 `AuditoriumRearFloorClosureSurface`로도 생성된다.

### 23.4 Radial 좌석 열 원호 프리뷰 정리

Radial 모드에는 각 좌석 열 위치를 보여주는 다음 보조 원호가 있었다.

- 일반 객석: 하늘색 원호
- 발코니: 보라색 원호

중앙 종단면을 확인할 때 이 원호들이 시야를 가리므로 다음 조건을
적용했다.

```python
show_radial_row_guides = (
    show_floor_surfaces or show_3d_seats
)
```

따라서 `Show floor surfaces`와 `Show 3D seat modules`를 모두 끄면
좌석 열 보조 원호를 화면의 `preview_curves`에 넣지 않는다.

다만 다음 데이터는 유지한다.

- 주황색 Radial 기준 원호
- Radial 계산 결과
- OK 시 생성할 `StallsRadialRow`, `Balcony01RadialRow`,
  `Balcony02RadialRow` Bake Curve

즉, 화면만 정리하며 계산 및 Bake 결과는 삭제하지 않는다.

### 23.5 1,000석 초과 프리뷰와 Bake 소스 분리

좌석 수가 많을 때의 성능을 위해 `AuditoriumSeat.3dm`의 다음 Curve
블록을 사용한다.

```text
TT_ChairBody_Crv
TT_Armrest_Crv
```

코드 기준 전환 조건은 다음과 같다.

```text
total_seat_count > 1000
```

정확히 1,000석까지는 Shaded Mesh 프리뷰이고, 1,001석부터 Curve
블록 프리뷰다.

기존 문제는 Curve 프리뷰용 컴포넌트 키가 `bake_instances`에도 그대로
들어가서, OK를 누르면 Curve 블록이 Bake되던 것이었다.

현재는 프리뷰와 Bake 소스를 명확히 분리한다.

| 좌석 수 | 화면 프리뷰 소스 | Bake 소스 |
|---:|---|---|
| 1,000 이하 | `chair`, `armrest`의 Shaded Mesh | `chair`, `armrest` 원본 3D 블록 |
| 1,000 초과 | `chair_curve`, `armrest_curve` | `chair`, `armrest` 원본 3D 블록 |

따라서 1,000석을 초과해도 `bake_instances`에는 항상 다음 키와 이름을
사용한다.

```text
chair   → ...Chair3D
armrest → ...Armrest3D
```

Curve 블록은 DisplayConduit 프리뷰에만 사용한다.

이 규칙은 다음 배치에 모두 동일하다.

- Stalls
- Balcony 1
- Balcony 2
- Rectangular
- Radial

이전에 이미 Curve 블록으로 Bake된 문서 객체는 자동 교체하지 않는다.
수정 이후 새로 실행한 `Auditorium` 명령의 Bake부터 원본 3D 블록을
사용한다.

### 23.6 오늘 변경된 생산 모듈

| 파일 | 주요 변경 |
|---|---|
| `constants.py` | 발코니 Offset 키와 최대 500열 상수 |
| `calculations/sections.py` | 최종 천장, Offset 기반 발코니 X, 최대 열 방어 |
| `section_interpolation_constants.py` | 좌석 상승 높이와 천장 구간 키 분리 |
| `main_dialog.py` | 기본값, 검증, 결과 문구, Override 수명주기 |
| `section_result_dialogs.py` | 천장 구간 입력, 최소값 보정, Eto 호환 |
| `balcony_settings_dialog.py` | 발코니 Offset UI와 실시간 프리뷰 |
| `preview_geometry.py` | 최종 천장·후벽, Offset 전파, Radial 원호 표시 조건 |
| `section_preview_annotations.py` | Offset 상태의 외곽 치수 연장선 |
| `geometry_metadata.py` | 후벽까지의 바닥 마감 면 이름 |
| `seat_preview_geometry.py` | Curve 프리뷰와 원본 3D Bake 소스 분리 |

다음 파일은 이번 좌석 Bake 수정에서 변경하지 않았다.

```text
document_baking.py
seat_source.py
AuditoriumSeat.3dm
```

`document_baking.py`는 `bake_instances`에 전달된 컴포넌트 키를 그대로
처리한다. 따라서 프리뷰 단계에서 Bake 키를 항상 `chair`와 `armrest`로
전달하도록 수정한 것이 핵심이다.

### 23.7 완료한 검사

작업 복사본과 실제 `ElephantTools 1.0.3` 설치 경로를 각각 직접 불러
다음 검사를 완료했다.

```text
AUDITORIUM_CEILING_OFFSET_SMOKE_PASS
AUDITORIUM_HOST_SMOKE_PASS
AUDITORIUM_SEAT_CURVE_SMOKE_PASS
```

검사 범위:

- 일반 객석만 있을 때의 천장 기준과 개구부 상단 보정
- Balcony 1 음수 Offset과 Balcony 2 양수 Offset의 독립성
- Balcony 2 기준 천장 구간
- 가장 뒤쪽 객석층을 따르는 후벽 X
- 직사각형 및 Radial 바닥·천장·후벽 면 생성
- 일반 객석 후방 통로 폭과 별도 후벽 바닥 마감
- 극단적인 Offset의 0열 판정과 500열 상한
- 천장 구간 입력 UI와 발코니 Offset UI 생성
- 기존 Proscenium/Open·Podium 프리뷰 회귀
- 일반석, 발코니 및 Radial 좌석 배치 회귀
- 1,002석에서 Curve 블록 프리뷰 전환
- Curve 프리뷰 상태의 `bake_instances`가 원본 3D 키를 유지하는지 확인
- Headless Rhino 문서에서 실제 Bake 실행
- Bake 후 `ChairBody3D`, `Armrest3D` 정의만 생성되고
  `ChairBodyCurve`, `ArmrestCurve` 정의는 생성되지 않는지 확인

실제 패키지에 반영한 뒤 작업본과 설치본 파일의 SHA-256 해시가 같은지도
확인했다.

### 23.8 오늘 변경분 빠른 확인 순서

1. Rhino에서 기존 Auditorium 설정창을 닫는다.
2. `Auditorium` 명령을 다시 실행한다.
3. `Section Dimension Control`을 연다.
4. 최상층 마지막 플랫폼~천장 높이를 입력한다.
5. 너무 작은 값을 입력했을 때 천장이 개구부 상단보다 내려가지 않는지
   확인한다.
6. Balcony 1·2 설정에서 양수와 음수 Offset을 각각 입력한다.
7. 각 발코니의 마지막 열 위치와 후벽이 독립적으로 갱신되는지 확인한다.
8. 바닥 면과 3D 좌석을 모두 끄고 Radial 모드를 확인한다.
9. 하늘색·보라색 좌석 열 보조 원호가 숨겨지는지 확인한다.
10. 1,001석 이상의 배치에서 화면은 Curve 블록으로 보이는지 확인한다.
11. OK 후 원본 3D 의자와 팔걸이 블록이 Bake되는지 확인한다.

---

## 24. 선택 Curve를 따른 좌석 배열 아이디어

오늘 가능성을 논의했지만 코드는 작성하지 않았다.

현재 Auditorium 코드에서 재사용할 수 있는 기능:

- `AuditoriumSeat.3dm`의 의자·팔걸이 로딩
- 블록 원점과 작성된 Z Offset 유지
- 의자 본체만 폭 방향 스케일
- 팔걸이 폭 고정
- 공유 팔걸이 배치
- Transform 생성
- 경량 프리뷰와 원본 3D Bake 소스 분리

새 명령을 만든다면 다음 배치 엔진이 추가로 필요하다.

1. 사용자가 하나 이상의 기준 Curve 선택
2. Curve 길이를 좌석 폭과 간격으로 분할
3. 각 배치점에서 Curve 접선 계산
4. 접선과 World Z로 좌석의 좌우축·관객 방향축 구성
5. 시작·끝 여백과 잔여 길이의 중앙 정렬
6. 좌석 사이 공유 팔걸이 배치
7. Curve 방향 반전 및 의자가 바라볼 방향 전환
8. 폐곡선, PolyCurve 꺾임, 작은 곡률 반지름 처리
9. 필요 시 2D Curve 프리뷰와 원본 3D Instance Bake

권장 독립 명령 이름의 예:

```text
SeatArrayOnCurve
```

초기 버전은 수평 평면 Curve만 지원하고, 이후 3D Curve와 복수 열
Offset으로 확장하는 편이 안전하다.
