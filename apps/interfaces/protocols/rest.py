from .base import ProtocolAdapter


class RestAdapter(ProtocolAdapter):
    code = 'REST'
    success_rate = 0.96
    latency_range = (40, 350)
    error_messages = ('HTTP 500 Internal Server Error', 'HTTP 504 Gateway Timeout', 'Connection refused')

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
            auth_line = f'X-API-Key: ***\n'

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
