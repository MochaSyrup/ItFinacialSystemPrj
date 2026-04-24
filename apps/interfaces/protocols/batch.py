import random
import shlex
import subprocess

from django.conf import settings

from .base import ExecutionResult, ProtocolAdapter


class BatchAdapter(ProtocolAdapter):
    code = 'BATCH'
    success_rate = 0.93
    latency_range = (1000, 6000)
    error_messages = ('Exit code 1: data validation failed', 'Exit code 137: out of memory', 'Script not found')

    # ── Mock 요약 ──
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

    # ── Live 경로 ──
    def _execute_live(self, interface) -> ExecutionResult:
        cfg = interface.config_json or {}
        script = cfg.get('script')
        args = cfg.get('args') or []
        timeout = int(cfg.get('timeout_sec') or getattr(settings, 'INTERFACE_BATCH_TIMEOUT', 3600))

        req_summary = self.build_request(interface)
        if not script:
            return ExecutionResult(
                success=False, latency_ms=0,
                request_summary=req_summary,
                error='script 경로가 비어 있습니다',
            )

        # 문자열로 받으면 shlex 로 분리 (쉘 주입 방지를 위해 shell=False)
        if isinstance(args, str):
            args = shlex.split(args)
        cmd = [script, *map(str, args)]

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True, text=True,
                timeout=timeout, shell=False, check=False,
            )
        except subprocess.TimeoutExpired:
            return ExecutionResult(
                success=False, latency_ms=timeout * 1000,
                request_summary=req_summary,
                error=f'Timeout after {timeout}s',
            )
        except FileNotFoundError:
            return ExecutionResult(
                success=False, latency_ms=0,
                request_summary=req_summary,
                error=f'script not found: {script}',
            )
        except Exception as exc:
            return ExecutionResult(
                success=False, latency_ms=0,
                request_summary=req_summary,
                error=f'{type(exc).__name__}: {exc}',
            )

        output = (proc.stdout or '') + (('\n[stderr]\n' + proc.stderr) if proc.stderr else '')
        success = proc.returncode == 0
        return ExecutionResult(
            success=success, latency_ms=0,
            request_summary=req_summary,
            response_summary=f'exit {proc.returncode}\n{output}' if success else '',
            error='' if success else f'exit {proc.returncode}: {(proc.stderr or proc.stdout or "")[:400]}',
        )
