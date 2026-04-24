from django.conf import settings

from .base import AdapterLibraryMissing, ExecutionResult, ProtocolAdapter


class RestAdapter(ProtocolAdapter):
    code = 'REST'
    success_rate = 0.96
    latency_range = (40, 350)
    error_messages = ('HTTP 500 Internal Server Error', 'HTTP 504 Gateway Timeout', 'Connection refused')

    # ── Mock 요약 ──
    def build_request(self, interface):
        cfg = interface.config_json or {}
        method = cfg.get('method', 'GET')
        auth = cfg.get('auth') or {}
        auth_line = ''
        if auth.get('type') == 'bearer':
            auth_line = 'Authorization: Bearer ***\n'
        elif auth.get('type') == 'basic':
            auth_line = 'Authorization: Basic ***\n'
        elif auth.get('type') == 'api_key':
            auth_line = 'X-API-Key: ***\n'

        headers = cfg.get('headers') or {'Accept': 'application/json'}
        hdr_lines = ''.join(f'{k}: {v}\n' for k, v in headers.items())

        qp = cfg.get('query_params') or {}
        qs = ''
        if qp:
            qs = '?' + '&'.join(f'{k}={v}' for k, v in qp.items())

        op_label = interface.get_operation_type_display() if interface.operation_type else 'REST 조회'
        return (
            f'[{op_label}]\n'
            f'{method} {interface.endpoint or ""}{qs}\n'
            f'Host: {interface.target_system or "unknown"}\n'
            f'{hdr_lines}'
            f'{auth_line}'
        )

    def build_response(self, interface):
        return (
            'HTTP/1.1 200 OK\n'
            'Content-Type: application/json\n\n'
            '{"status":"ok","interface":"' + interface.code + '","rows":42}'
        )

    # ── Live 경로 ──
    def _execute_live(self, interface) -> ExecutionResult:
        try:
            import requests
        except ImportError as exc:
            raise AdapterLibraryMissing('requests 미설치') from exc

        cfg = interface.config_json or {}
        method = (cfg.get('method') or 'GET').upper()
        url = interface.endpoint or ''
        if not url:
            return ExecutionResult(
                success=False, latency_ms=0,
                request_summary=self.build_request(interface),
                error='endpoint 가 비어 있습니다',
            )
        headers = dict(cfg.get('headers') or {'Accept': 'application/json'})
        query = cfg.get('query_params') or {}
        body = cfg.get('body')
        timeout = int(cfg.get('timeout_sec') or getattr(settings, 'INTERFACE_HTTP_TIMEOUT', 30))

        # 인증 헤더
        auth = cfg.get('auth') or {}
        auth_type = auth.get('type')
        auth_obj = None
        if auth_type == 'bearer' and auth.get('token'):
            headers['Authorization'] = f'Bearer {auth["token"]}'
        elif auth_type == 'basic' and auth.get('user'):
            auth_obj = (auth.get('user', ''), auth.get('password', ''))
        elif auth_type == 'api_key' and auth.get('key'):
            header_name = auth.get('header') or 'X-API-Key'
            headers[header_name] = auth['key']

        # 요약에는 민감 정보 마스킹
        req_summary = self.build_request(interface)

        try:
            resp = requests.request(
                method=method, url=url,
                headers=headers, params=query or None,
                json=body if isinstance(body, (dict, list)) else None,
                data=body if isinstance(body, str) else None,
                auth=auth_obj, timeout=timeout,
            )
        except requests.Timeout:
            return ExecutionResult(
                success=False, latency_ms=timeout * 1000,
                request_summary=req_summary,
                error=f'Timeout after {timeout}s',
            )
        except requests.RequestException as exc:
            return ExecutionResult(
                success=False, latency_ms=0,
                request_summary=req_summary,
                error=f'{type(exc).__name__}: {exc}',
            )

        latency = int(resp.elapsed.total_seconds() * 1000) if resp.elapsed else 0
        status = resp.status_code
        body_text = resp.text or ''
        success = 200 <= status < 300
        summary = f'HTTP/1.1 {status} {resp.reason}\nContent-Type: {resp.headers.get("Content-Type", "")}\n\n{body_text}'
        return ExecutionResult(
            success=success,
            latency_ms=latency,
            request_summary=req_summary,
            response_summary=summary if success else '',
            error='' if success else f'HTTP {status}: {body_text[:200]}',
        )
