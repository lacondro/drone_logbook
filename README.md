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
- **포맷 자동 판별 (매직 바이트 기준)**: `.bin` 파일이라도 내용이 PX4 ULog인지
  ArduPilot DataFlash인지 헤더로 판별해 올바른 파서로 라우팅. (확장자 무시)
- **리스트 뷰**: 날짜 / 비행시간 / 거리 / 조종사 / 파일명 정렬, 기체·스택·
  날짜범위·텍스트(파일/조종사/특이사항) 필터.
- **상세 뷰**: Flight Review 레이아웃 — 좌측 기체·펌웨어 블록, 우측 비행 통계
  블록, **Leaflet 위성 지도**(Esri World Imagery, 토큰 불필요) + GPS 트랙,
  그리고 **Logged Messages** 테이블.
- **기체 관리**: 감지된 기체 UID에 등록번호/별명/메모를 매핑, 기체별 필터,
  비행을 다른 기체로 **수동 재할당**(ArduPilot은 깔끔한 UUID가 없어 보완).
- **비행별 조종사 / 특이사항**: 로그 파일에 없는 데이터이므로 SQLite에 저장.
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
> 입력하면 백엔드가 그 폴더를 스캔합니다. 따라서 로그가 있는 PC에서 실행하세요.

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

1. 프로젝트 전체를 NAS에 올립니다(또는 Git 저장소로 연결).
2. [`docker-compose.yml`](docker-compose.yml)의 볼륨 경로를 실제 NAS 로그 공유
   경로로 바꿉니다:
   ```yaml
   volumes:
     - /volume1/flightlogs:/logs   # 왼쪽 = NAS 실제 경로, 오른쪽 = 고정(/logs)
   ```
3. **Portainer → Stacks → Add stack**에서 이 compose로 배포합니다
   (Repository 또는 Web editor). Portainer가 이미지를 빌드합니다.
4. 브라우저에서 **http://<NAS-IP>:8137** 접속. 스캔 경로는 `/logs`로 자동 채워지니
   **Scan**만 누르면 됩니다.

참고:
- 컨테이너는 `0.0.0.0:8137`로 떠서 사내망 어디서든 접속됩니다.
- `LOGBOOK_DEFAULT_FOLDER=/logs` 환경변수로 기본 폴더가 고정되어, 재시작 후에도
  같은 폴더 DB를 자동으로 엽니다.
- **인증이 없으므로 신뢰된 사내망에서만** 사용하세요. 여러 사람이 서로 다른 폴더를
  동시에 스캔하는 용도는 아닙니다(공용 폴더 1개 전제).
- ARM 기반 NAS는 빌드 시 일부 의존성을 컴파일할 수 있습니다(`build-essential` 포함).

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

## 사용법

1. 앱을 열고 스캔 바에 폴더 경로(예: `C:\Users\me\flightlogs`)를 입력한 뒤
   필요하면 **Recursive** 체크, **Scan** 클릭.
2. 비행 리스트를 둘러보고, 행을 클릭하면 상세 뷰 + 지도가 열립니다.
3. **Vehicles** 메뉴에서 등록번호를 지정하면, 리스트의 기체 필터가 등록번호
   기준으로 동작합니다.
4. 비행 상세 페이지에서 **Pilot** / **Remarks** 입력 및 (필요 시) 다른 기체로
   재할당 후 **Save entry**.

PX4·ArduPilot 예제가 들어있는 `sample_logs/` 폴더가 포함되어 있습니다 —
`…/drone_logbook/sample_logs` 를 스캔하면 바로 체험할 수 있습니다.

---

## CLI (파서 단독 확인)

```bash
cd backend
.venv/Scripts/python cli.py ../sample_logs/px4_sample.ulg --no-track --no-msgs
.venv/Scripts/python cli.py ../sample_logs/ardupilot_log2_ku.bin
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
| POST   | `/api/scan` | `{path, recursive}` 폴더 스캔, `{scanned, parsed_new, skipped_cached, failed, folder, db_path}` 반환 |
| GET    | `/api/flights` | 필터(`vehicle_uid`,`stack`,`date_from`,`date_to`,`q`)·정렬(`sort`,`order`) 리스트 |
| GET    | `/api/flights/{id}` | 상세(트랙 GeoJSON + logged messages 포함) |
| PATCH  | `/api/flights/{id}` | `pilot` / `remarks` / `vehicle_uid`(재할당) 수정 |
| GET    | `/api/vehicles` | 기체 목록(+비행 수, 마지막 비행) |
| PATCH  | `/api/vehicles/{uid}` | `registration_number` / `nickname` / `notes` 수정 |

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
- **시작 위치(시군구)**: 스캔 후 시작 GPS 좌표를 OpenStreetMap Nominatim으로
  역지오코딩해 시/군/구(예: 영월군, 강동구)를 채웁니다. 인터넷이 필요하며,
  좌표를 ~1 km로 반올림해 캐시(같은 비행장은 1회 호출)하고 1초 간격으로
  요청합니다. 실패하면 위치는 비워둡니다(스캔은 영향 없음).
- 트랙은 저장/전송을 위해 최대 400점으로 다운샘플링됩니다.
