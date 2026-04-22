from apps.interfaces.models import InterfaceLog

from .base import ExecutionResult, ProtocolAdapter
from .batch import BatchAdapter
from .mq import MqAdapter
from .rest import RestAdapter
from .sftp import SftpAdapter
from .soap import SoapAdapter

ADAPTERS = {
    'REST': RestAdapter(),
    'SOAP': SoapAdapter(),
    'MQ': MqAdapter(),
    'SFTP': SftpAdapter(),
    'BATCH': BatchAdapter(),
}


def execute_interface(interface):
    """Mock 실행: 어댑터 호출 → InterfaceLog 생성 후 반환."""
    adapter = ADAPTERS[interface.protocol]
    result = adapter.execute(interface)
    return InterfaceLog.objects.create(
        interface=interface,
        status=InterfaceLog.Status.SUCCESS if result.success else InterfaceLog.Status.FAIL,
        latency_ms=result.latency_ms if result.success else None,
        request_summary=result.request_summary,
        response_summary=result.response_summary,
        error=result.error,
    )


__all__ = ['ADAPTERS', 'ExecutionResult', 'ProtocolAdapter', 'execute_interface']
