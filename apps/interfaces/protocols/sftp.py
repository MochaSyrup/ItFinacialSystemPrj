import random

from .base import ProtocolAdapter


class SftpAdapter(ProtocolAdapter):
    code = 'SFTP'
    success_rate = 0.97
    latency_range = (500, 3000)
    error_messages = ('Permission denied (publickey)', 'No such file or directory', 'Disk quota exceeded')

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
        # UPLOAD
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
