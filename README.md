# 보험사 금융 IT 포탈

보험사 금융 IT 시스템의 **인터페이스 통합관리**와 **금융상품 평가 포트폴리오**를 제공하는 Django 기반 웹 포탈입니다.

## 주요 기능

### 1. 인터페이스 통합관리 (`/interfaces/`)
- 지원 프로토콜: **REST API, SOAP, MQ, SFTP/FTP, Batch**
- 인터페이스 등록 / 설정 / 활성화 토글 / 수동 실행
- 호출 로그 조회 및 실패 건 재처리
- 프로토콜별 어댑터 구조 (`apps/interfaces/protocols/`)

### 2. 금융상품 평가 (`/evaluation/`)
- 평가 대상: **주식, 채권, 파생상품, 프로젝트 사업**
- 산출 지표:
  - 주식: VaR (95%, 1d), 연 변동성
  - 채권: 가격, Macaulay Duration, Convexity
  - 파생: 레버리지 기반 실효 노출 VaR
  - 프로젝트: NPV, IRR
- 포트폴리오 집계: 총 평가액 / 총 VaR / 평균 듀레이션 / 비중 한도 초과 알람

### 3. 모니터링 대시보드 (`/`)
- 등록 인터페이스 / 오늘 호출 건수 / 실패율 / 평균 응답시간 KPI
- 시간대별 호출 추이 (Chart.js)
- 프로토콜 분포, 최근 실행 로그, 빠른 실행 패널

## 기술 스택

| 영역 | 사용 기술 |
|---|---|
| Framework | Django 5.1 (풀스택 Template + HTMX) |
| API | Django REST Framework + drf-spectacular (OpenAPI) |
| UI | Django Template + HTMX + Bootstrap Icons + Chart.js |
| DB | PostgreSQL 15 (배포), SQLite (개발 기본) |
| 비동기 | Celery + Redis + Celery Beat (예정) |
| 인증 | Django Auth (Session + Group 기반 권한) |
| 배포 | Docker Compose (web / worker / beat / postgres / redis / mock-rest / mock-sftp) |

## 프로젝트 구조

```
ClaudePrject/
├── apps/
│   ├── accounts/         # 사용자/권한
│   ├── core/             # 공통 (템플릿 태그, 컨텍스트 프로세서)
│   ├── evaluation/       # 금융상품 평가
│   │   ├── metrics.py      # VaR / Duration / NPV / IRR 계산
│   │   └── models.py       # Portfolio, FinancialProduct
│   ├── interfaces/       # 인터페이스 통합관리
│   │   ├── protocols/      # REST/SOAP/MQ/SFTP/BATCH 어댑터
│   │   └── models.py       # Interface, InterfaceLog
│   └── monitoring/       # 대시보드
├── portal/               # Django 프로젝트 설정
├── templates/            # Django 템플릿
├── static/               # CSS/JS
├── mockup/               # UI 목업
├── manage.py
└── requirements.txt
```

## 시작하기

### 요구사항
- Python 3.12+
- (선택) PostgreSQL 15, Redis

### 설치 및 실행

```bash
# 1. 저장소 클론
git clone https://github.com/MochaSyrup/ItFinacialSystemPrj.git
cd ItFinacialSystemPrj

# 2. 가상환경 생성 및 의존성 설치
python -m venv venv
venv\Scripts\activate         # Windows
# source venv/bin/activate    # macOS/Linux
pip install -r requirements.txt

# 3. DB 마이그레이션
python manage.py migrate

# 4. (선택) 시드 데이터 생성
python manage.py seed_interfaces
python manage.py seed_portfolios

# 5. 관리자 계정 생성
python manage.py createsuperuser

# 6. 개발 서버 실행
python manage.py runserver
```

브라우저에서 http://127.0.0.1:8000 접속.

## 주요 URL

| 경로 | 설명 |
|---|---|
| `/` | 모니터링 대시보드 |
| `/interfaces/` | 인터페이스 목록 |
| `/interfaces/new/` | 인터페이스 등록 |
| `/interfaces/logs/` | 호출 로그 |
| `/evaluation/portfolios/` | 포트폴리오 목록 |
| `/evaluation/products/` | 금융상품 목록 |
| `/evaluation/risk/` | 리스크 분석 |
| `/admin/` | Django 관리자 |

## 데이터 모델

- **Interface**: 인터페이스 등록 정보 (프로토콜, 엔드포인트, 스케줄, 설정 JSON)
- **InterfaceLog**: 호출 로그 (상태, 응답시간, 요청/응답 요약, 오류)
- **Portfolio**: 포트폴리오 (기준 통화, 평가 기준일, 비중 한도)
- **FinancialProduct**: 금융상품 (종류, 명목금액, 장부가, 평가 지표 JSON)

## 평가 지표 계산

`apps/evaluation/metrics.py` — 순수 Python 구현:

- `npv(cashflows, rate)` / `irr(cashflows)` — 현재가치/내부수익률
- `bond_price`, `macaulay_duration`, `convexity` — 채권 지표
- `parametric_var(notional, sigma_annual, days, z)` — 파라메트릭 VaR (95% z=1.6449)
- `compute(product)` — 상품 종류별 평가
- `aggregate(products)` — 포트폴리오 집계 (총 평가액, VaR, 비중 한도 체크)

## 개발 메모

- 설정 파일: `portal/settings.py`
- 기본 DB: SQLite (`db.sqlite3`) — gitignore에 포함됨
- 인터페이스 실행은 현재 **Mock** 어댑터 사용 (`apps/interfaces/protocols/`)
