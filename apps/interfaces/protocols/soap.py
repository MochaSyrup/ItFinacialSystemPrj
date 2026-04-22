from .base import ProtocolAdapter


class SoapAdapter(ProtocolAdapter):
    code = 'SOAP'
    success_rate = 0.92
    latency_range = (200, 800)
    error_messages = ('SOAP Fault: server.userException', 'WSDL parse error', 'XML schema validation failed')

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
