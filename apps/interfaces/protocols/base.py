"""프로토콜 어댑터 공통 인프라

- Mock 모드: 랜덤 성공/실패 시나리오 생성 (개발·데모·테스트 기본)
- Live 모드: 실제 라이브러리로 호출. 라이브러리 미설치 시 Mock 으로 자동 폴백
- 공통: 재시도, 타임아웃, response 길이 제한, 레이턴시 측정
"""
import random
import time
from dataclasses import dataclass

from django.conf import settings


class AdapterLibraryMissing(RuntimeError):
    """실제 어댑터 실행에 필요한 라이브러리가 설치되지 않음"""


@dataclass
class ExecutionResult:
    success: bool
    latency_ms: int
    request_summary: str
    response_summary: str = ''
    error: str = ''


@dataclass
class ProtocolAdapter:
    """프로토콜 어댑터 베이스.

    - `execute(interface)` 가 엔트리포인트
    - live/mock 은 전역 settings.INTERFACE_LIVE_MODE + config_json.live 로 결정
    - 하위 클래스는 `_execute_live(interface)` 를 구현. 미구현이면 Mock 으로 폴백.
    """
    code: str = ''
    # Mock 시나리오 파라미터
    success_rate: float = 0.95
    latency_range: tuple = (50, 300)
    error_messages: tuple = ('Connection timeout', 'Network unreachable')

    # ── 엔트리포인트 ──────────────────────────────────────
    def execute(self, interface) -> ExecutionResult:
        max_chars = getattr(settings, 'INTERFACE_RESPONSE_MAX_CHARS', 4000)
        retry_max = getattr(settings, 'INTERFACE_RETRY_MAX', 1)
        backoff = getattr(settings, 'INTERFACE_RETRY_BACKOFF', 0.5)

        last_result = None
        for attempt in range(retry_max + 1):
            result = self._dispatch_once(interface)
            result.request_summary = _truncate(result.request_summary, max_chars)
            result.response_summary = _truncate(result.response_summary, max_chars)
            result.error = _truncate(result.error, max_chars)
            if result.success:
                if attempt:
                    result.response_summary = f'(재시도 {attempt}회 성공)\n' + result.response_summary
                return result
            last_result = result
            if attempt < retry_max:
                time.sleep(backoff * (2 ** attempt))
        return last_result

    # ── 모드 디스패치 ──────────────────────────────────────
    def _dispatch_once(self, interface) -> ExecutionResult:
        if self._is_live(interface):
            started = time.perf_counter()
            try:
                result = self._execute_live(interface)
                if result.latency_ms == 0:
                    result.latency_ms = int((time.perf_counter() - started) * 1000)
                return result
            except AdapterLibraryMissing as exc:
                # lib 미설치 → mock 으로 폴백하되 error 메모는 남김
                fallback = self._execute_mock(interface)
                fallback.error = f'[live 모드 fallback: {exc}] {fallback.error}'.strip()
                return fallback
            except Exception as exc:
                latency = int((time.perf_counter() - started) * 1000)
                return ExecutionResult(
                    success=False, latency_ms=latency,
                    request_summary=self.build_request(interface),
                    error=f'{type(exc).__name__}: {exc}',
                )
        return self._execute_mock(interface)

    def _is_live(self, interface) -> bool:
        cfg = interface.config_json or {}
        if 'live' in cfg:
            return bool(cfg['live'])
        return bool(getattr(settings, 'INTERFACE_LIVE_MODE', False))

    # ── Mock 경로 (기존 동작 유지) ──────────────────────
    def _execute_mock(self, interface) -> ExecutionResult:
        success = random.random() < self.success_rate
        latency = random.randint(*self.latency_range)
        req = self.build_request(interface)
        if success:
            return ExecutionResult(
                success=True, latency_ms=latency,
                request_summary=req, response_summary=self.build_response(interface),
            )
        return ExecutionResult(
            success=False, latency_ms=latency,
            request_summary=req, error=random.choice(self.error_messages),
        )

    # ── Live 경로 (하위 클래스가 오버라이드) ───────────────
    def _execute_live(self, interface) -> ExecutionResult:
        raise AdapterLibraryMissing(f'{self.code} live 어댑터 미구현')

    # ── 공통 요약 포맷 ─────────────────────────────────────
    def build_request(self, interface) -> str:
        return f'{self.code} {interface.endpoint or interface.code}'

    def build_response(self, interface) -> str:
        return '200 OK'


def _truncate(text: str, limit: int) -> str:
    if not text or len(text) <= limit:
        return text or ''
    return text[:limit] + f'\n… (truncated {len(text) - limit} chars)'
