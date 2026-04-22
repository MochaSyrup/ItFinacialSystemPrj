import random
import uuid

from .base import ProtocolAdapter


class MqAdapter(ProtocolAdapter):
    code = 'MQ'
    success_rate = 0.94
    latency_range = (10, 80)
    error_messages = ('Queue full', 'Broker unreachable', 'Message TTL expired', 'Deserialize failed')

    def build_request(self, interface):
        cfg = interface.config_json or {}
        qm = cfg.get('queue_manager', 'QM_DEFAULT')
        queue = cfg.get('queue') or interface.endpoint or 'UNKNOWN.Q'
        channel = cfg.get('channel', 'DEFAULT.SVRCONN')
        op = interface.operation_type or 'MQ_PUBLISH'

        if op == 'MQ_PUBLISH':
            return (
                f'[MQ 발행]\n'
                f'PUT {qm}/{queue} (channel={channel})\n'
                f'message-id: {uuid.uuid4()}\n'
                f'payload: <{interface.code}><data>...</data></{interface.code}>'
            )
        if op == 'MQ_CONSUME':
            return (
                f'[MQ 수신]\n'
                f'GET {qm}/{queue} (channel={channel}, wait=30s)\n'
                f'poll for messages...'
            )
        # MQ_CONSUME_PROCESS
        table = cfg.get('save_to_table', f'{interface.code.lower()}_inbox')
        return (
            f'[MQ 수신 → 가공 → 저장]\n'
            f'GET {qm}/{queue}\n'
            f'  → parse payload\n'
            f'  → transform\n'
            f'  → INSERT INTO {table} (...)'
        )

    def build_response(self, interface):
        op = interface.operation_type or 'MQ_PUBLISH'
        if op == 'MQ_PUBLISH':
            return f'ACK message-id={uuid.uuid4()}'
        if op == 'MQ_CONSUME':
            n = random.randint(1, 20)
            return f'received {n} messages'
        # CONSUME_PROCESS
        n = random.randint(1, 20)
        return f'received {n} messages\nprocessed {n} rows\ncommitted to DB'
