import random
from dataclasses import dataclass, field


@dataclass
class ExecutionResult:
    success: bool
    latency_ms: int
    request_summary: str
    response_summary: str = ''
    error: str = ''


@dataclass
class ProtocolAdapter:
    """프로토콜 어댑터 베이스 — 실제 통신 대신 mock 결과를 만든다.

    하위 클래스는 success_rate / latency_range / 포맷 메서드를 오버라이드.
    """
    code: str = ''
    success_rate: float = 0.95
    latency_range: tuple = (50, 300)
    error_messages: tuple = ('Connection timeout', 'Network unreachable')

    def execute(self, interface) -> ExecutionResult:
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

    def build_request(self, interface) -> str:
        return f'{self.code} {interface.endpoint or interface.code}'

    def build_response(self, interface) -> str:
        return '200 OK'
