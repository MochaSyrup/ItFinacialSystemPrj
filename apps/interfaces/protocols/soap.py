from django.conf import settings

from .base import AdapterLibraryMissing, ExecutionResult, ProtocolAdapter


class SoapAdapter(ProtocolAdapter):
    code = 'SOAP'
    success_rate = 0.92
    latency_range = (200, 800)
    error_messages = ('SOAP Fault: server.userException', 'WSDL parse error', 'XML schema validation failed')

    # ── Mock 요약 ──
    def build_request(self, interface):
        cfg = interface.config_json or {}
        wsdl = cfg.get('wsdl') or (interface.endpoint or '')
        op = cfg.get('operation', 'query')
        auth = cfg.get('auth') or {}
        sec_header = ''
        if auth.get('type') == 'ws-security':
            sec_header = (
                '<wsse:Security>\n'
                f'  <wsse:UsernameToken><wsse:Username>{auth.get("user", "")}</wsse:Username>'
                '<wsse:Password>***</wsse:Password></wsse:UsernameToken>\n'
                '</wsse:Security>\n'
            )

        op_label = interface.get_operation_type_display() if interface.operation_type else 'SOAP 조회'
        return (
            f'[{op_label}]\n'
            f'POST {wsdl}\n'
            f'SOAPAction: "{op}"\n'
            f'{sec_header}'
            f'<soap:Envelope><soap:Body>\n'
            f'  <{op}Request><code>{interface.code}</code></{op}Request>\n'
            f'</soap:Body></soap:Envelope>'
        )

    def build_response(self, interface):
        cfg = interface.config_json or {}
        op = cfg.get('operation', 'query')
        return (
            '<soap:Envelope><soap:Body>\n'
            f'  <{op}Response><code>0</code><msg>OK</msg><count>17</count></{op}Response>\n'
            '</soap:Body></soap:Envelope>'
        )

    # ── Live 경로 ──
    def _execute_live(self, interface) -> ExecutionResult:
        try:
            from zeep import Client
            from zeep.exceptions import Fault
            from zeep.transports import Transport
            from requests import Session
        except ImportError as exc:
            raise AdapterLibraryMissing('zeep/requests 미설치') from exc

        cfg = interface.config_json or {}
        wsdl = cfg.get('wsdl') or interface.endpoint
        if not wsdl:
            return ExecutionResult(
                success=False, latency_ms=0,
                request_summary=self.build_request(interface),
                error='wsdl 경로가 비어 있습니다',
            )

        op = cfg.get('operation')
        if not op:
            return ExecutionResult(
                success=False, latency_ms=0,
                request_summary=self.build_request(interface),
                error='operation 이름이 필요합니다',
            )

        timeout = int(cfg.get('timeout_sec') or getattr(settings, 'INTERFACE_HTTP_TIMEOUT', 30))
        args = cfg.get('args') or {}

        session = Session()
        auth = cfg.get('auth') or {}
        if auth.get('type') == 'basic' and auth.get('user'):
            session.auth = (auth.get('user', ''), auth.get('password', ''))

        req_summary = self.build_request(interface)
        try:
            client = Client(wsdl, transport=Transport(session=session, timeout=timeout))
            service_op = getattr(client.service, op)
            result = service_op(**args) if isinstance(args, dict) else service_op(*args)
        except Fault as exc:
            return ExecutionResult(
                success=False, latency_ms=0,
                request_summary=req_summary,
                error=f'SOAP Fault: {exc.message}',
            )
        except Exception as exc:
            return ExecutionResult(
                success=False, latency_ms=0,
                request_summary=req_summary,
                error=f'{type(exc).__name__}: {exc}',
            )

        return ExecutionResult(
            success=True, latency_ms=0,
            request_summary=req_summary,
            response_summary=str(result),
        )
