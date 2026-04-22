# 프로젝트: 보험사 금융 IT 포탈

## 목적
보험사 금융 IT 인터페이스 통합관리 + 금융상품 평가 포트폴리오

## 기술 스택
- Framework: Django 5 풀스택 (Template + HTMX)
- API: Django REST Framework + drf-spectacular (OpenAPI)
- UI: Django Template + HTMX + Tailwind/Bootstrap + Bootstrap Icons + Chart.js
- DB/ORM: Django ORM + PostgreSQL 15 (dev fallback: SQLite)
- 비동기: Celery + Redis + Celery Beat
- 인증: Django Auth (Session + Group 기반 권한)
- 배포: Docker Compose (web / worker / beat / postgres / redis / mock-rest / mock-sftp)

## 시스템 1: 인터페이스 통합관리
- 프로토콜: REST API, SOAP, MQ, Batch, SFTP/FTP
- 기능: 등록/설정/활성화/모니터링/로그/재처리

## 시스템 2: 금융상품 평가
- 대상: 주식, 채권, 파생상품, 프로젝트 사업
- 지표: VaR, Duration, Convexity, NPV, IRR

## DB 주요 테이블
- interfaces: 인터페이스 등록 정보
- interface_logs: 호출 로그
- portfolios: 포트폴리오
- financial_products: 금융상품
