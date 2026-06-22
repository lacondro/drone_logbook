# Drone Flight Logbook (비행 로그북)

지정한 폴더의 PX4(`.ulg`) / ArduPilot(`.bin`) 비행 로그를 일괄 로드하여
**정리·검색·기록**하는 로컬 웹앱입니다. 폴더를 가리키면 모든 로그를 파싱해
리스트로 보여주고, 로그별 기체·비행 요약 + GPS 지도를 확인하며, 기체 등록번호·
조종사·특이사항을 기록할 수 있습니다.

이 도구는 **로그북**이지 분석 툴이 아닙니다 — 시계열 플롯/PID/FFT 같은 분석은
의도적으로 제외했습니다(그건 [PX4 Flight Review](https://review.px4.io/),
[ArduPilot UAV Log Viewer](https://plot.ardupilot.org/) 를 사용).

---

## 주요 기능

- **폴더 스캔**: `.ulg` / `.bin` 로그 (하위 폴더 재귀 옵션), size+mtime **캐시**로
  재스캔 시 신규/변경 로그만 파싱.
- **업로드**: 브라우저에서 로컬 `.ulg`/`.bin`을 **서버(NAS) 로그 폴더로 직접
  업로드**. NAS 컨테이너는 클라이언트 PC 디스크를 못 읽으므로, 원격에서 로그를
  올릴 때 유용. 업로드 후 자동으로 스캔되어 리스트에 반영.
- **중복 방지**: 같은 로그가 이름만 다르거나 다른 포맷으로 들어와도 한 번만
  등록. ① **내용 해시(SHA-256)**로 바이트가 같은 파일, ② **기체 UID + 시작시각**
  으로 같은 비행을 감지해 스킵(스캔 결과에 `dup N`으로 표시).
- **포맷 자동 판별 (매직 바이트 기준)**: `.bin` 파일이라도 내용이 PX4 ULog인지
  ArduPilot DataFlash인지 헤더로 판별해 올바른 파서로 라우팅. (확장자 무시)
- **리스트 뷰**: 날짜 / 비행시간 / 거리 / 조종사 / 파일명 정렬, 기체·스택·
  날짜범위·텍스트(파일/조종사/특이사항/**위치(시군구)**) 필터.
- **상세 뷰**: Flight Review 레이아웃 — 좌측 기체·펌웨어 블록, 우측 비행 통계
  블록, **Leaflet 위성 지도**(Esri World Imagery, 토큰 불필요) + GPS 트랙,
  그리고 **Logged Messages** 테이블.
- **기체 관리**: 감지된 기체 UID에 등록번호/별명/메모를 매핑, 기체별 필터,
  비행을 다른 기체로 **수동 재할당**(ArduPilot은 깔끔한 UUID가 없어 보완).
  **Aircrafts** 페이지에서 기체를 **직접 추가**(로그 없이도)하거나, 비행이 없는
  기체를 **삭제**할 수 있음.
- **조종사 로스터**: **Pilots** 페이지에서 조종사를 **추가/삭제**(로스터). 비행에
  쓰인 조종사는 자동 집계되고, 비행이 없는 로스터 항목만 삭제 가능.
- **비행별 조종사 / 특이사항**: 로그 파일에 없는 데이터이므로 SQLite에 저장.
- **다중 선택 일괄 지정**: 리스트에서 여러 로그를 체크해 **조종사·기체를 한 번에**
  지정(예: 같은 비행일에 시동만 한 로그들을 묶어 일괄 처리). 페이지를 넘어가도
  선택이 유지됨.
- **비행 삭제**: 상세 뷰에서 비행을 로그북에서 제거 + (확인 후) **디스크의 로그
  파일까지 영구 삭제**. "시동만 해본 로그" 정리에 유용 — 파일을 지워야 재스캔에서
  다시 살아나지 않음.
- **자동 정리(유령 행 제거)**: 스캔할 때 디스크에 더 이상 존재하지 않는 경로의
  DB 행을 자동 제거 → 폴더 이동/이름변경으로 생긴 중복을 방지. (마운트가 끊겨
  모든 파일이 사라진 것처럼 보이면 통째 삭제를 막는 안전장치 포함)
- **에러 내성**: 손상되거나 GPS 없는 로그가 섞여 있어도 스캔 전체가 죽지 않고,
  리스트에 `error` / `partial` 상태와 사유가 표시됨.

---

## 기술 스택

| 영역     | 선택                                                  |
|----------|-------------------------------------------------------|
| 파싱     | Python — `pyulog`(PX4), `pymavlink`(ArduPilot)        |
| 백엔드   | FastAPI + SQLite                                       |
| 프론트   | React (Vite) + react-router                            |
| 지도     | Leaflet + Esri World Imagery 타일 (Mapbox 토큰 불필요) |

Python 3.14 / Node 24 (Windows 11)에서 검증. 테스트한 라이브러리 버전은
[`backend/requirements.txt`](backend/requirements.txt) 와
[`frontend/package.json`](frontend/package.json) 에 고정되어 있습니다.

---

## 실행 방법

> 브라우저가 로컬 디스크를 직접 읽지 않습니다 — 앱에 **서버 측 폴더 경로**를
> 입력하면 백엔드가 그 폴더를 스캔합니다. 따라서 로그가 있는 PC에서 실행하거나,
> 원격(NAS)이라면 **Upload** 버튼으로 로컬 파일을 서버로 전송하세요.

### 방법 A — 단일 포트 (가장 간단, 데모 권장)

프론트를 빌드해서 API + UI를 FastAPI 한 포트(**http://localhost:8137**)로 서빙.
실행하면 브라우저가 자동으로 열립니다.

```powershell
# Windows PowerShell
./serve.ps1
```

### 방법 B — 개발 모드 (핫 리로드)

백엔드 `:8137`, Vite 개발 서버 **http://localhost:5173** (`/api`는 백엔드로 프록시).

```powershell
# Windows PowerShell
./dev.ps1
```

```bash
# macOS / Linux / Git-Bash
./dev.sh
```

### 방법 C — NAS / Docker (Portainer, 사내 공용)

NAS에 올려 사내에서 같이 쓰는 구성입니다. **하나의 공용 로그 폴더**를 컨테이너의
`/logs`에 마운트하고, 로그북 DB는 `/logs/flightlogbook.db`에 저장되어 로그와 함께
NAS에 남습니다.

> **왜 NAS에서 직접 빌드하지 않나?** Portainer가 NAS에서 Dockerfile을 빌드하게 하면,
> 사내망이 데비안 패키지 서버(`deb.debian.org`)를 막거나 NAS 사양이 낮을 때
> `apt-get` 단계에서 실패합니다. 그래서 **PC에서 이미지를 빌드해 `tar`로 만들고,
> NAS(Portainer)는 그 이미지를 받아 실행만** 하는 방식을 씁니다.

자세한 명령어는 아래 [이미지 빌드 & NAS 배포](#이미지-빌드--nas-배포-portainer) 참고.
배포 후 브라우저에서 **http://&lt;NAS-IP&gt;:8137** 접속 → 스캔 경로가 `/logs`로 자동
채워지니 **Scan**만 누르면 됩니다.

참고:
- 컨테이너는 `0.0.0.0:8137`로 떠서 사내망 어디서든 접속됩니다.
- `LOGBOOK_DEFAULT_FOLDER=/logs` 환경변수로 기본 폴더가 고정되어, 재시작 후에도
  같은 폴더 DB를 자동으로 엽니다.
- **인증이 없으므로 신뢰된 사내망에서만** 사용하세요. 여러 사람이 서로 다른 폴더를
  동시에 스캔하는 용도는 아닙니다(공용 폴더 1개 전제).
- **비행 삭제** 기능을 쓰려면 컨테이너가 `/logs`(NAS 공유폴더)에 **쓰기/삭제 권한**이
  있어야 합니다(공유폴더가 읽기전용이면 DB 행만 지워지고 파일은 안 지워짐).

### 수동 실행

```bash
# 백엔드
cd backend
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt   # Windows
# .venv/bin/pip install -r requirements.txt                # POSIX
.venv/Scripts/python -m uvicorn main:app --reload --port 8137

# 프론트엔드 (다른 셸에서)
cd frontend
npm install
npm run dev      # http://localhost:5173
```

---

## 이미지 빌드 & NAS 배포 (Portainer)

> 사내 NAS에 올릴 때 쓰는 전체 절차. **PC(Docker Desktop)에서 빌드 → `tar`로 저장 →
> Portainer에 업로드 → 스택 배포**. NAS는 컴파일을 안 하고 받은 이미지를 실행만 함.

### 0) 준비 (최초 1회)
- PC(Windows)에 **Docker Desktop** 설치 후 **앱 실행** → 우하단 고래 아이콘이
  "Engine running"인지 확인. (엔진이 꺼져 있으면 `docker build`가
  `dockerDesktopLinuxEngine ... cannot find the file` 에러)
- NAS에 로그용 공유폴더 준비 후 **절대경로** 확인 (예: Synology `/volume1/WizFlightHub/logs`).

### 1) 이미지 빌드 (PC, 프로젝트 폴더에서)
```powershell
docker build -t drone-logbook:latest .
```
NAS가 **ARM**이면 아키텍처를 맞춰 빌드:
```powershell
docker build --platform linux/arm64 -t drone-logbook:latest .
```
> NAS CPU 확인: Portainer 첫 화면, 또는 NAS SSH에서 `uname -m`
> (`x86_64` → amd64 / `aarch64` → arm64). **이미지 arch ≠ NAS arch면 실행 안 됨.**

### 2) tar로 내보내기
```powershell
docker save drone-logbook:latest -o drone-logbook.tar
```

### 3) Portainer에 이미지 업로드
- **Portainer → Images → Import** → `drone-logbook.tar` 선택 → Upload
- (tar가 커서 브라우저 업로드가 느리면: tar를 NAS 공유폴더에 복사 후 SSH에서
  `docker load -i /volume1/.../drone-logbook.tar`)
- 업로드되면 Images 목록에 `drone-logbook:latest`가 보임.

### 4) 스택 배포
- **Portainer → Stacks → Add stack** → 이름 `drone-logbook` → **Web editor**
- [`docker-compose.yml`](docker-compose.yml) 내용을 붙여넣고, 볼륨 경로를 NAS에 맞춤:
  ```yaml
  volumes:
    - /volume1/WizFlightHub/logs:/logs   # 왼쪽=NAS 실제 경로 : 오른쪽=고정(/logs)
  ```
  ⚠️ `:/logs`(컨테이너 경로)를 **빼먹지 말 것** — 빼면 폴더가 연결되지 않음.
- **Deploy the stack**
- 만약 `docker.io`에서 받으려다 실패하면(`pull access denied` 등), `image:` 아래에
  로컬 이미지만 쓰도록 한 줄 추가:
  ```yaml
    pull_policy: never
  ```

### 5) 접속
**http://&lt;NAS-IP&gt;:8137** → **Scan** (스캔 경로 `/logs`는 자동).

### 코드 수정 후 업데이트 (재빌드)
> 백엔드/프론트 코드를 바꾸면 이미지를 **다시 빌드**해야 NAS에 반영됨 (단순 데이터 문제는 재빌드 불필요).
```powershell
# PC, 프로젝트 폴더
docker build -t drone-logbook:latest .
docker save drone-logbook:latest -o drone-logbook.tar
```
그다음 Portainer에서:
1. **Images** → 기존 `drone-logbook:latest` 선택 → **Remove**
2. **Images → Import** → 새 `drone-logbook.tar` 업로드
3. **Stacks** → 해당 스택 → **Update / Redeploy** (또는 stack을 Stop 후 Start)

---

## 사용법

1. 앱을 열고 스캔 바에 폴더 경로(예: `C:\Users\me\flightlogs`)를 입력한 뒤
   필요하면 **Recursive** 체크, **Scan** 클릭.
   - 또는 **Upload** 버튼으로 로컬 `.ulg`/`.bin`을 **서버 로그 폴더로 올릴 수
     있습니다**(NAS처럼 서버가 내 PC를 못 읽는 경우 유용). 업로드 후 자동 스캔.
2. 비행 리스트를 둘러보고, 행을 클릭하면 상세 뷰 + 지도가 열립니다.
3. **Aircrafts** 메뉴에서 등록번호를 지정하면, 리스트의 기체 필터가 등록번호
   기준으로 동작합니다.
4. 비행 상세 페이지에서 **Pilot** / **Remarks** 입력 및 (필요 시) 다른 기체로
   재할당 후 **Save entry**. 더 이상 필요 없는 로그는 **Delete flight**로 제거
   (디스크 파일까지 삭제).
5. **여러 로그 일괄 지정**: 리스트에서 카드 왼쪽 체크박스(또는 헤더 체크박스로
   페이지 전체)를 선택하면 위에 일괄 바가 뜹니다. **Pilot** 입력 / **기체 선택**
   후 **Apply** → 선택한 모든 로그에 한 번에 반영.

PX4·ArduPilot 예제가 들어있는 `sample_logs/` 폴더가 포함되어 있습니다 —
`…/drone_logbook/sample_logs` 를 스캔하면 바로 체험할 수 있습니다.

---

## CLI (파서 단독 확인)

```bash
cd backend
.venv/Scripts/python cli.py ../sample_logs/04_13_14.ulg --no-track --no-msgs
.venv/Scripts/python cli.py ../sample_logs/log_0_2026-6-12-11-09-06.bin
```

---

## 프로젝트 구조

```
drone_logbook/
├─ backend/
│  ├─ parsers/            # common.py, px4_parser.py, ardupilot_parser.py
│  ├─ db.py               # SQLite 스키마 + 커넥션
│  ├─ scanner.py          # 폴더 스캔 + 캐시 + 파싱
│  ├─ main.py             # FastAPI 앱 (scan / flights / vehicles)
│  ├─ cli.py              # 로그 1개 파싱 → JSON
│  └─ requirements.txt
├─ frontend/              # React (Vite)
│  └─ src/                # pages/ (FlightList, FlightDetail, Vehicles), components/MapTrack
├─ sample_logs/           # 예제 .ulg / .bin
├─ dev.ps1 / dev.sh       # 개발 런처 (2포트, 핫 리로드)
└─ serve.ps1              # 단일 포트 빌드 + 서빙
```

---

## API 요약

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET    | `/api/status` | 현재 활성 로그북 폴더 / DB 경로 / 비행 수 |
| POST   | `/api/scan` | `{path, recursive}` 폴더 스캔, `{scanned, parsed_new, skipped_cached, failed, duplicates, pruned_missing, folder, db_path}` 반환 (`duplicates`=중복으로 스킵, `pruned_missing`=사라진 파일의 행 자동 제거 수) |
| POST   | `/api/upload` | multipart 파일 업로드(`.ulg`/`.bin`) → 활성 로그북 폴더에 저장 후 스캔, `{uploaded, skipped, duplicates, ...scan}` 반환 |
| GET    | `/api/flights` | 필터(`vehicle_uid`,`stack`,`date_from`,`date_to`,`q`=파일/조종사/특이사항/위치/등록번호)·정렬(`sort`,`order`) 리스트 |
| GET    | `/api/flights/{id}` | 상세(트랙 GeoJSON + logged messages 포함) |
| PATCH  | `/api/flights/{id}` | `pilot` / `remarks` / `vehicle_uid`(재할당) 수정 |
| POST   | `/api/flights/bulk` | `{ids, pilot?, vehicle_uid?}` 여러 비행에 조종사/기체 일괄 지정 |
| DELETE | `/api/flights/{id}` | 비행 삭제. `?delete_file=true`면 디스크의 로그 파일도 삭제(로그북 폴더 내 파일만, 안전) |
| GET    | `/api/vehicles` | 기체 목록(+비행 수, 마지막 비행) |
| POST   | `/api/vehicles` | 기체 수동 추가(`registration_number`/`nickname`/`notes`) → 합성 UID 생성 |
| PATCH  | `/api/vehicles/{uid}` | `registration_number` / `nickname` / `notes` 수정 |
| DELETE | `/api/vehicles/{uid}` | 기체 삭제(비행 0건일 때만; 사용 중이면 409) |
| GET    | `/api/pilots` | 조종사별 집계(로스터 + 비행에서 파생, 0건 로스터 포함) |
| POST   | `/api/pilots` | 조종사 로스터 추가(`{name}`) |
| DELETE | `/api/pilots/{name}` | 조종사 로스터 삭제(비행 0건일 때만; 사용 중이면 409) |

---

## 데이터 저장 위치 (중요)

로그북 DB는 **스캔한 폴더 안**에 `flightlogbook.db` 파일로 생성됩니다. 파싱
캐시와 사용자 입력(조종사 / 특이사항 / 등록번호)이 모두 이 한 파일에 들어가므로,
**로그 폴더를 옮기면 주석도 함께 따라갑니다.**

- 서버는 마지막으로 스캔한 폴더를 기억해(`backend/.active_db`) 재시작 시 자동으로
  다시 엽니다. 재스캔 없이 이전 입력이 그대로 보입니다.
- 다른 폴더를 스캔하면 그 폴더의 `flightlogbook.db`로 전환됩니다(폴더별 독립 로그북).
- 첫 실행(스캔 전)에는 `backend/logbook.db`(빈 기본 DB)를 사용합니다.

> 저장 방식이 폴더 내 DB로 바뀌었기 때문에, 이전에 `backend/logbook.db`에 입력했던
> 데이터는 새 폴더 DB에 자동 이전되지 않습니다. 폴더를 다시 스캔하면 됩니다.

---

## 참고 / 한계

- **ArduPilot 기체 식별**: 부팅 배너의 보드 CPU id가 있으면 그것으로, 없으면
  보드+펌웨어 기반의 약한 id를 사용합니다. 매칭이 틀리면 상세 뷰의 재할당으로
  교정하세요.
- **시각**: GPS 기준 UTC로 저장하고 로컬 시간으로 표시합니다. GPS 픽스가 없는
  로그는 절대 시각/트랙/거리가 없으며 `partial`로 표시됩니다.
- **중복 판정**: 바이트가 같은 파일은 내용 해시로 항상 잡지만, **같은 비행 판정은
  기체 UID + 시작시각**에 의존합니다. 따라서 GPS(시작시각)가 없는 로그는 내용
  해시로만 비교되고, 드물게 같은 기체가 같은 시각으로 기록된 서로 다른 로그를
  같다고 볼 수 있습니다. 중복은 **새로 추가만 막을 뿐**, 기존 파일/행은 삭제하지
  않습니다.
- **시작 위치(시군구)**: 스캔 후 시작 GPS 좌표를 OpenStreetMap Nominatim으로
  역지오코딩해 시/군/구(예: 영월군, 강동구)를 채웁니다. 인터넷이 필요하며,
  좌표를 ~1 km로 반올림해 캐시(같은 비행장은 1회 호출)하고 1초 간격으로
  요청합니다. 실패하면 위치는 비워둡니다(스캔은 영향 없음).
- 트랙은 저장/전송을 위해 최대 400점으로 다운샘플링됩니다.
