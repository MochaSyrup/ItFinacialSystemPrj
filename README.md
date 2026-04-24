# 보험사 금융 IT 포탈

보험사 금융 IT 시스템의 **인터페이스 통합관리**, **금융상품 평가 포트폴리오**, 그리고 **원가/관리회계**를 제공하는 Django 기반 웹 포탈입니다.

## 주요 기능

### 1. 인터페이스 통합관리 (`/interfaces/`)
- 지원 프로토콜: **REST API, SOAP, MQ, SFTP/FTP, Batch**
- 인터페이스 등록 / 설정 / 활성화 토글 / 수동 실행
- **구조화 입력 폼** — 프로토콜별 개별 필드 (REST method/auth/headers·query, SOAP wsdl/operation, MQ queue_manager/queue/channel, SFTP host/port/user, BATCH script/args). JSON 직접 편집 없음, 저장 시 `config_json` 자동 조립
- **cron 5필드 validator** — 스케줄 입력 검증 (`*`, `a-b`, `*/n`, 쉼표 목록, 필드별 범위 체크)
- **인터페이스 상세 페이지** (`/interfaces/<pk>/`) — KPI(성공률/평균 응답시간) + 민감 키 마스킹된 config + 최근 20건 실행 로그
- 목록 페이징 (25건/page), 키워드/프로토콜 필터
- 호출 로그 조회 및 **실패 건 일괄 재처리** — 선택/전체 모드, 동일 인터페이스 중복 자동 병합 (최대 100건)
- 프로토콜별 어댑터 구조 (`apps/interfaces/protocols/`)

### 2. 금융상품 평가 (`/evaluation/`)
- 평가 대상: **주식, 채권, 파생상품, 프로젝트 사업**
- **구조화 등록 폼** — 종류별 개별 필드 입력, 저장 시 `metrics_json` 자동 조립
  - 주식: 현재가 / 보유수량 / 연 변동성 σ
  - 채권: par / 쿠폰금리 / YTM / 만기(년)
  - 파생: notional / 레버리지 / 변동성 / 기준가
  - 프로젝트: 할인율 / 현금흐름 (쉼표·줄바꿈 구분, t=0 투자 음수)
- 산출 지표:
  - 주식: 파라메트릭 VaR (95%, 1d), Historical VaR, 연 변동성
  - 채권: 가격, Macaulay Duration, Convexity, YTM 시계열
  - 파생: 레버리지 기반 실효 노출 VaR + 변동성 시계열
  - 프로젝트: NPV, IRR, 할인율 시계열
- 포트폴리오 집계: 총 평가액 / 총 VaR / 평균 듀레이션 / 비중 한도 초과 알람
- **시세 히스토리 (`PriceHistory`)** — 상품별 365일 가격/수익률/변동성/YTM 시계열
- **스트레스 테스트** — 금리 ±bp / 주가 ±% / 변동성 ×N / 복합 위기 7개 시나리오. 포트폴리오 평가액 변화 + 상품별 기여도 분석

### 3. 원가/관리회계 (`/evaluation/costing/`)
IT 금융 플랫폼사의 **조직 단위 P&L 시스템**. 프로젝트 단위 수익성 분석 + 공통비 배분까지 end-to-end.

- **조직 마스터** — 본부(Division) / 부서(Department) / 인력(Employee, 직급별 월 표준인건비)
- **프로젝트** — 계약금액·예산·공수, 원가센터 유형, 배분 키, `ProjectBudget` 항목별 예산 분해
- **원가 원장 (`CostEntry`)** — 실집행 원가 기록 (수동 입력, 월 인건비 자동 안분, 배분 결과)
- **수익 원장 (`RevenueEntry`)** — 실현 매출 기록
- **월 인건비 자동 안분** — `ProjectAssignment.allocation_pct` 기준으로 월 표준인건비를 프로젝트별로 쪼개 원장에 자동 기입
- **표준원가 배분 엔진**
  - Driver 5종: `HEADCOUNT` / `MANHOUR` / `REVENUE` / `EQUAL` / `MANUAL`
  - 배분 대상 차원 3종: `PROJECT` / `DEPARTMENT` / `EMPLOYEE`
  - **시뮬 → 확정 → 취소(Reverse)** 워크플로우
  - 확정 시 출발 부서에 `-총액` **상쇄 CostEntry 자동 생성** (이중계상 방지, 보존 법칙 유지)
- **손익 대시보드** — 기간 필터, 전사 매출/원가/이익/이익률 KPI, 원가 구성 도넛차트, 본부별 P&L, 프로젝트 Top10 / Bottom10

### 4. 모니터링 대시보드 (`/`)
- 등록 인터페이스 / 오늘 호출 건수 / 실패율 / 평균 응답시간 KPI
- 시간대별 호출 추이 (Chart.js)
- 프로토콜 분포, 최근 실행 로그, 빠른 실행 패널

## 기술 스택

| 영역 | 사용 기술 |
|---|---|
| Framework | Django 5.1 (풀스택 Template + HTMX) |
| API | Django REST Framework + drf-spectacular (OpenAPI) |
| UI | Django Template + HTMX + Tailwind (CDN) + Bootstrap Icons + Chart.js |
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
│   ├── evaluation/       # 금융상품 평가 + 원가/관리회계
│   │   ├── metrics.py      # VaR / Duration / NPV / IRR / Historical VaR 계산
│   │   ├── stress.py       # 스트레스 테스트 엔진 (금리/주가/변동성 쇼크)
│   │   ├── costing.py      # 월 인건비 안분 + 표준원가 배분 엔진
│   │   ├── models.py       # Portfolio·Product·PriceHistory + Division·Department·Employee·Project·CostEntry·RevenueEntry·AllocationRule 등
│   │   └── management/commands/
│   │       ├── seed_costing_master.py         # 5본부/15부서/50명/20프로젝트 시드
│   │       ├── seed_costing_transactions.py   # 4개월치 원가/매출/배분 트랜잭션 시드
│   │       ├── seed_portfolios.py             # 포트폴리오/상품 간이 시드
│   │       ├── seed_market_data.py            # 3포트폴리오×~30상품 + 365일 시세 히스토리
│   │       └── allocate_salary.py             # 월 인건비 안분 CLI
│   ├── interfaces/       # 인터페이스 통합관리
│   │   ├── protocols/      # REST/SOAP/MQ/SFTP/BATCH 어댑터
│   │   ├── forms.py        # 프로토콜별 구조화 폼 + cron validator
│   │   ├── utils.py        # 민감 키 마스킹 (mask_config)
│   │   └── models.py       # Interface, InterfaceLog
│   └── monitoring/       # 대시보드
├── portal/               # Django 프로젝트 설정
├── templates/            # Django 템플릿 (costing_*.html, allocation_*.html 포함)
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
python manage.py seed_interfaces             # 인터페이스 샘플
python manage.py seed_market_data --reset    # 포트폴리오 3개 × ~30 상품 + 365일 시세
python manage.py seed_costing_master         # 원가/관리회계 마스터 (5본부/15부서/50명/20프로젝트)
python manage.py seed_costing_transactions   # 원가/관리회계 4개월치 트랜잭션 (원가·매출·배분)

# 5. 관리자 계정 생성
python manage.py createsuperuser

# 6. 개발 서버 실행
python manage.py runserver
```

브라우저에서 http://127.0.0.1:8000 접속.

### 월 인건비 안분 (CLI)

```bash
python manage.py allocate_salary 2026-04           # 해당 월 안분 실행
python manage.py allocate_salary 2026-04 --reset   # 기존 SALARY 항목 삭제 후 재생성
```

## 주요 URL

| 경로 | 설명 |
|---|---|
| `/` | 모니터링 대시보드 |
| `/interfaces/` | 인터페이스 목록 (페이징·필터) |
| `/interfaces/new/` | 인터페이스 등록 (프로토콜별 구조화 폼) |
| `/interfaces/<pk>/` | 인터페이스 상세 (KPI + 마스킹 config + 최근 로그) |
| `/interfaces/execute/` | 수동 실행 · 실패 일괄 재시도 |
| `/interfaces/logs/` | 호출 로그 |
| `/evaluation/portfolios/` | 포트폴리오 목록 |
| `/evaluation/products/` | 금융상품 목록 |
| `/evaluation/risk/` | 리스크 분석 |
| `/evaluation/costing/` | **손익 대시보드 (P&L)** |
| `/evaluation/costing/divisions/` | 본부·부서 |
| `/evaluation/costing/employees/` | 인력 |
| `/evaluation/costing/projects/` | 프로젝트 |
| `/evaluation/costing/ledger/` | 원가 원장 |
| `/evaluation/costing/revenue/` | 수익 원장 |
| `/evaluation/costing/allocation/rules/` | 표준원가 배분 규칙 |
| `/evaluation/costing/allocation/runs/` | 배분 실행 이력 |
| `/admin/` | Django 관리자 |

## 데이터 모델

### 인터페이스 / 평가
- **Interface**: 인터페이스 등록 정보 (프로토콜, 엔드포인트, 스케줄, 설정 JSON)
- **InterfaceLog**: 호출 로그 (상태, 응답시간, 요청/응답 요약, 오류)
- **Portfolio / FinancialProduct**: 포트폴리오·금융상품 (평가 지표 JSON)

### 원가/관리회계
- **Division / Department / Employee**: 조직·인력 마스터 (직급별 월 표준인건비)
- **Project / ProjectBudget / ProjectAssignment**: 프로젝트 마스터, 항목별 예산, 인력 투입
- **CostCategory / CostEntry**: 원가 항목·원장 (immutable, 보정은 역분개)
- **RevenueEntry**: 수익 원장
- **InternalTransfer**: 부서간 내부거래 (elimination 대상)
- **AllocationRule / AllocationDriver**: 배분 규칙 + 수동 기준값
- **AllocationRun / AllocationResult**: 배분 실행 이력과 결과 (시뮬→확정→취소)

## 핵심 로직

### 평가 지표 (`apps/evaluation/metrics.py`)
순수 Python 구현:
- `npv(cashflows, rate)` / `irr(cashflows)` — 현재가치/내부수익률
- `bond_price`, `macaulay_duration`, `convexity` — 채권 지표
- `parametric_var(notional, sigma_annual, days, z)` — 파라메트릭 VaR (95% z=1.6449)
- `historical_var_rate(prices, confidence, days)` — 실측 시계열 기반 VaR (5% 분위수)
- `compute(product)` — 상품 종류별 평가 (평가액 + 지표 + 계산 근거 trace)
- `aggregate(products)` — 포트폴리오 집계 (총 평가액, VaR, 비중 한도 체크)

### 스트레스 테스트 (`apps/evaluation/stress.py`)
- 7개 기본 시나리오: 금리 ±100/50bp, 주가 -20/-10%, 변동성 ×1.5/×2.0, 복합 위기
- `_apply_shocks(product, shocks)` → 쇼크 적용된 proxy → `metrics.compute()` 재호출
- 반환: 포트폴리오 base/stressed 평가액, Δ금액/%, VaR 증가분, 상품별 기여도

### 원가 엔진 (`apps/evaluation/costing.py`)
- `allocate_monthly_salary(period, reset=False)` — 월 인건비 자동 안분
- `simulate_allocation(rule, period)` — 배분 시뮬 (`AllocationRun(SIMULATED)` + `AllocationResult` 생성, 원장 미변경)
- `commit_allocation(run)` — 확정 → 결과별 `CostEntry(source=ALLOCATION)` + 출발부서 상쇄 entry 생성
- `reverse_allocation(run)` — 확정 취소 → 생성된 CostEntry 전부 삭제

### Driver 계산 로직
| Driver | 기준 |
|---|---|
| `HEADCOUNT` | 대상별 활성 인원수 |
| `MANHOUR` | 기간 내 `ProjectAssignment.allocation_pct` 합 |
| `REVENUE` | `RevenueEntry.amount` 집계 |
| `EQUAL` | 대상 균등 분할 |
| `MANUAL` | `AllocationDriver` 에 수동 입력된 값 |

## 개발 메모

- 설정 파일: `portal/settings.py`
- 기본 DB: SQLite (`db.sqlite3`) — gitignore에 포함됨
- 인터페이스 실행은 현재 **Mock** 어댑터 사용 (`apps/interfaces/protocols/`)
- 한국어 UI · 한국 IT 금융 플랫폼사 조직/프로젝트 시나리오 기준 시드
