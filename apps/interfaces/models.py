from django.db import models


class Interface(models.Model):
    class Protocol(models.TextChoices):
        REST = 'REST', 'REST'
        SOAP = 'SOAP', 'SOAP'
        MQ = 'MQ', 'MQ'
        SFTP = 'SFTP', 'SFTP'
        BATCH = 'BATCH', 'Batch'

    class Operation(models.TextChoices):
        # REST
        REST_GET_QUERY = 'REST_GET_QUERY', 'REST 조회 (GET)'
        # SOAP
        SOAP_QUERY = 'SOAP_QUERY', 'SOAP 조회'
        # MQ
        MQ_PUBLISH = 'MQ_PUBLISH', 'MQ 발행'
        MQ_CONSUME = 'MQ_CONSUME', 'MQ 수신'
        MQ_CONSUME_PROCESS = 'MQ_CONSUME_PROCESS', 'MQ 수신 → 가공 → 저장'
        # SFTP
        SFTP_DOWNLOAD = 'SFTP_DOWNLOAD', 'SFTP 다운로드'
        SFTP_UPLOAD = 'SFTP_UPLOAD', 'SFTP 업로드'
        # Batch
        BATCH_SCHEDULED = 'BATCH_SCHEDULED', 'Batch 스케줄 실행'

    # 프로토콜 → 허용되는 operation 목록
    PROTOCOL_OPERATIONS = {
        'REST':  ['REST_GET_QUERY'],
        'SOAP':  ['SOAP_QUERY'],
        'MQ':    ['MQ_PUBLISH', 'MQ_CONSUME', 'MQ_CONSUME_PROCESS'],
        'SFTP':  ['SFTP_DOWNLOAD', 'SFTP_UPLOAD'],
        'BATCH': ['BATCH_SCHEDULED'],
    }

    code = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=128)
    protocol = models.CharField(max_length=8, choices=Protocol.choices)
    operation_type = models.CharField(
        max_length=24, choices=Operation.choices, blank=True,
        help_text='프로토콜별 세부 동작'
    )
    target_system = models.CharField(max_length=64, blank=True)
    endpoint = models.CharField(max_length=512, blank=True)
    schedule_cron = models.CharField(
        max_length=64, blank=True,
        help_text='cron 표기 (예: "0 2 * * *" = 매일 새벽 2시). BATCH/SFTP 일 때만 사용'
    )
    config_json = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.code} ({self.get_protocol_display()})'


class InterfaceLog(models.Model):
    class Status(models.TextChoices):
        SUCCESS = 'SUCCESS', '성공'
        FAIL = 'FAIL', '실패'

    interface = models.ForeignKey(Interface, on_delete=models.CASCADE, related_name='logs')
    executed_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=8, choices=Status.choices)
    latency_ms = models.IntegerField(null=True, blank=True)
    request_summary = models.TextField(blank=True)
    response_summary = models.TextField(blank=True)
    error = models.TextField(blank=True)

    class Meta:
        ordering = ['-executed_at']

    def __str__(self):
        return f'{self.interface.code} @ {self.executed_at:%Y-%m-%d %H:%M:%S}'
