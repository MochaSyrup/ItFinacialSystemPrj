import fnmatch
import os
import random

from django.conf import settings

from .base import AdapterLibraryMissing, ExecutionResult, ProtocolAdapter


class SftpAdapter(ProtocolAdapter):
    code = 'SFTP'
    success_rate = 0.97
    latency_range = (500, 3000)
    error_messages = ('Permission denied (publickey)', 'No such file or directory', 'Disk quota exceeded')

    # ── Mock 요약 ──
    def build_request(self, interface):
        cfg = interface.config_json or {}
        host = cfg.get('host', 'unknown-host')
        port = cfg.get('port', 22)
        user = cfg.get('user', 'user')
        remote = cfg.get('remote_path') or interface.endpoint or '/'
        pattern = cfg.get('file_pattern', '*')
        op = interface.operation_type or 'SFTP_DOWNLOAD'

        if op == 'SFTP_DOWNLOAD':
            return (
                f'[SFTP 다운로드]\n'
                f'connect sftp://{user}@{host}:{port}\n'
                f'cd {remote}\n'
                f'mget {pattern}'
            )
        filename = f'{interface.code}_{random.randint(10000, 99999)}.csv'
        return (
            f'[SFTP 업로드]\n'
            f'connect sftp://{user}@{host}:{port}\n'
            f'put {filename}\n'
            f'→ {remote}{filename}'
        )

    def build_response(self, interface):
        op = interface.operation_type or 'SFTP_DOWNLOAD'
        size = random.randint(10, 2000)
        secs = random.randint(1, 5)
        if op == 'SFTP_DOWNLOAD':
            files = random.randint(1, 12)
            return f'downloaded {files} files, {size} KB in {secs}s'
        return f'uploaded 1 file, {size} KB in {secs}s'

    # ── Live 경로 ──
    def _execute_live(self, interface) -> ExecutionResult:
        try:
            import paramiko
        except ImportError as exc:
            raise AdapterLibraryMissing('paramiko 미설치') from exc

        cfg = interface.config_json or {}
        host = cfg.get('host')
        port = int(cfg.get('port') or 22)
        user = cfg.get('user')
        remote = cfg.get('remote_path') or '/'
        pattern = cfg.get('file_pattern') or '*'
        op = interface.operation_type or 'SFTP_DOWNLOAD'
        local_dir = cfg.get('local_path') or '.'
        timeout = int(cfg.get('timeout_sec') or getattr(settings, 'INTERFACE_SFTP_TIMEOUT', 30))

        req_summary = self.build_request(interface)
        if not host or not user:
            return ExecutionResult(
                success=False, latency_ms=0, request_summary=req_summary,
                error='host/user 가 필요합니다',
            )

        auth_kwargs = {}
        if cfg.get('auth') == 'key' and cfg.get('key_path'):
            auth_kwargs['key_filename'] = cfg['key_path']
        elif cfg.get('password'):
            auth_kwargs['password'] = cfg['password']
        else:
            return ExecutionResult(
                success=False, latency_ms=0, request_summary=req_summary,
                error='auth=key 또는 password 필요',
            )

        transport = None
        try:
            transport = paramiko.Transport((host, port))
            transport.connect(username=user, **auth_kwargs)
            sftp = paramiko.SFTPClient.from_transport(transport)

            if op == 'SFTP_DOWNLOAD':
                try:
                    sftp.chdir(remote)
                except IOError as exc:
                    return ExecutionResult(
                        success=False, latency_ms=0, request_summary=req_summary,
                        error=f'remote_path {remote}: {exc}',
                    )
                files = [f for f in sftp.listdir('.') if fnmatch.fnmatch(f, pattern)]
                os.makedirs(local_dir, exist_ok=True)
                bytes_total = 0
                for f in files:
                    local_path = os.path.join(local_dir, f)
                    sftp.get(f, local_path)
                    bytes_total += os.path.getsize(local_path)
                summary = f'downloaded {len(files)} files, {bytes_total // 1024} KB → {local_dir}'
                return ExecutionResult(
                    success=True, latency_ms=0,
                    request_summary=req_summary, response_summary=summary,
                )

            # UPLOAD
            local_files = cfg.get('upload_files') or []
            if not local_files:
                return ExecutionResult(
                    success=False, latency_ms=0, request_summary=req_summary,
                    error='upload_files 리스트가 비어 있습니다',
                )
            try:
                sftp.chdir(remote)
            except IOError:
                sftp.mkdir(remote)
                sftp.chdir(remote)
            bytes_total = 0
            for lp in local_files:
                sftp.put(lp, os.path.basename(lp))
                bytes_total += os.path.getsize(lp)
            summary = f'uploaded {len(local_files)} files, {bytes_total // 1024} KB → {host}:{remote}'
            return ExecutionResult(
                success=True, latency_ms=0,
                request_summary=req_summary, response_summary=summary,
            )
        except paramiko.SSHException as exc:
            return ExecutionResult(
                success=False, latency_ms=0, request_summary=req_summary,
                error=f'SSH: {exc}',
            )
        except Exception as exc:
            return ExecutionResult(
                success=False, latency_ms=0, request_summary=req_summary,
                error=f'{type(exc).__name__}: {exc}',
            )
        finally:
            if transport:
                transport.close()
