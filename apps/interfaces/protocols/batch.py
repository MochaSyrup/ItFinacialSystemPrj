import random

from .base import ProtocolAdapter


class BatchAdapter(ProtocolAdapter):
    code = 'BATCH'
    success_rate = 0.93
    latency_range = (1000, 6000)
    error_messages = ('Exit code 1: data validation failed', 'Exit code 137: out of memory', 'Script not found')

    def build_request(self, interface):
        cfg = interface.config_json or {}
        script = cfg.get('script') or interface.endpoint or interface.code
        args = cfg.get('args') or []
        timeout = cfg.get('timeout_sec', 3600)
        cron = interface.schedule_cron or '(수동)'

        args_line = ' '.join(args) if args else ''
        return (
            f'[Batch 스케줄 실행]\n'
            f'schedule: {cron}\n'
            f'timeout: {timeout}s\n'
            f'EXEC {script} {args_line}'.rstrip()
        )

    def build_response(self, interface):
        rows = random.randint(100, 50000)
        dur = random.randint(500, 5000)
        return f'exit 0\nprocessed {rows:,} rows in {dur}ms'
