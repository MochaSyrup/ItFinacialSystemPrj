import json
import random
import uuid

from django.conf import settings

from .base import AdapterLibraryMissing, ExecutionResult, ProtocolAdapter


class MqAdapter(ProtocolAdapter):
    code = 'MQ'
    success_rate = 0.94
    latency_range = (10, 80)
    error_messages = ('Queue full', 'Broker unreachable', 'Message TTL expired', 'Deserialize failed')

    # ── Mock 요약 ──
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
        n = random.randint(1, 20)
        return f'received {n} messages\nprocessed {n} rows\ncommitted to DB'

    # ── Live 경로 (AMQP / RabbitMQ 지원, IBM MQ 는 별도 구현 필요) ──
    def _execute_live(self, interface) -> ExecutionResult:
        cfg = interface.config_json or {}
        broker = (cfg.get('broker') or 'amqp').lower()
        if broker != 'amqp':
            raise AdapterLibraryMissing(
                f'broker={broker} 미지원 (AMQP 만 지원, IBM MQ 는 pymqi 별도 필요)'
            )

        try:
            import pika
        except ImportError as exc:
            raise AdapterLibraryMissing('pika 미설치') from exc

        host = cfg.get('host') or 'localhost'
        port = int(cfg.get('port') or 5672)
        queue = cfg.get('queue')
        op = interface.operation_type or 'MQ_PUBLISH'
        req_summary = self.build_request(interface)
        if not queue:
            return ExecutionResult(
                success=False, latency_ms=0,
                request_summary=req_summary,
                error='queue 이름이 비어 있습니다',
            )

        auth = cfg.get('auth') or {}
        credentials = pika.PlainCredentials(
            auth.get('user', 'guest'), auth.get('password', 'guest'),
        )
        params = pika.ConnectionParameters(
            host=host, port=port, credentials=credentials,
            socket_timeout=int(cfg.get('timeout_sec') or getattr(settings, 'INTERFACE_HTTP_TIMEOUT', 30)),
        )

        conn = None
        try:
            conn = pika.BlockingConnection(params)
            ch = conn.channel()
            ch.queue_declare(queue=queue, durable=cfg.get('durable', True), passive=False)

            if op == 'MQ_PUBLISH':
                body = cfg.get('body') or {'code': interface.code}
                payload = json.dumps(body).encode('utf-8') if isinstance(body, (dict, list)) else str(body).encode('utf-8')
                ch.basic_publish(
                    exchange=cfg.get('exchange', ''), routing_key=queue, body=payload,
                    properties=pika.BasicProperties(delivery_mode=2),
                )
                return ExecutionResult(
                    success=True, latency_ms=0,
                    request_summary=req_summary,
                    response_summary=f'published to {queue} ({len(payload)} bytes)',
                )

            # CONSUME / CONSUME_PROCESS — 배치성으로 큐에 쌓인 메시지 최대 N 개 drain
            max_msgs = int(cfg.get('max_messages') or 10)
            received = []
            for _ in range(max_msgs):
                method, _props, body = ch.basic_get(queue=queue, auto_ack=False)
                if method is None:
                    break
                received.append((method.delivery_tag, body))

            if op == 'MQ_CONSUME':
                for tag, _ in received:
                    ch.basic_ack(tag)
                return ExecutionResult(
                    success=True, latency_ms=0,
                    request_summary=req_summary,
                    response_summary=f'received {len(received)} messages',
                )

            # MQ_CONSUME_PROCESS — 실제 DB 저장은 운영 환경마다 상이하므로 pass-through
            # (save_to_table 지정 시 여기서 INSERT 처리 훅을 덧붙여야 함)
            for tag, _ in received:
                ch.basic_ack(tag)
            return ExecutionResult(
                success=True, latency_ms=0,
                request_summary=req_summary,
                response_summary=(
                    f'received {len(received)} messages\n'
                    f'note: save_to_table 처리는 프로젝트별 훅 필요 (pass-through)'
                ),
            )
        except Exception as exc:
            return ExecutionResult(
                success=False, latency_ms=0,
                request_summary=req_summary,
                error=f'{type(exc).__name__}: {exc}',
            )
        finally:
            if conn and not conn.is_closed:
                conn.close()
