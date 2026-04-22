import random
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.interfaces.models import Interface, InterfaceLog

SEED = [
    ('IF_FSS_DAILY_REPORT', '금감원 일일 보고',      'REST',  '금감원',      'https://api.fss.or.kr/v1/reports/daily'),
    ('IF_FSS_MONTHLY_STAT', '금감원 월간 통계',      'REST',  '금감원',      'https://api.fss.or.kr/v1/stats/monthly'),
    ('IF_PARTNER_CLAIM',    '제휴사 보험금 청구',    'SOAP',  '제휴사 A',    'https://partner-a.example.com/claims?wsdl'),
    ('IF_PARTNER_POLICY',   '제휴사 계약 조회',      'SOAP',  '제휴사 B',    'https://partner-b.example.com/policy?wsdl'),
    ('IF_CORE_POLICY_SYNC', '코어 계약 동기화',      'MQ',    '코어시스템',  'queue://core.policy.sync'),
    ('IF_CORE_PAYMENT',     '코어 결제 이벤트',      'MQ',    '코어시스템',  'queue://core.payment.events'),
    ('IF_SFTP_ACCOUNTING',  '회계 전표 전송',        'SFTP',  '회계시스템',  'sftp://accounting.internal/in/'),
    ('IF_BATCH_NIGHTLY',    '야간 정산 배치',        'BATCH', '정산배치',    '/opt/batch/nightly.sh'),
]


class Command(BaseCommand):
    help = '인터페이스 + 호출 로그 샘플 데이터를 생성합니다.'

    def add_arguments(self, parser):
        parser.add_argument('--reset', action='store_true', help='기존 데이터 삭제 후 재생성')
        parser.add_argument('--logs', type=int, default=40, help='생성할 로그 건수')

    def handle(self, *args, **opts):
        if opts['reset']:
            InterfaceLog.objects.all().delete()
            Interface.objects.all().delete()
            self.stdout.write(self.style.WARNING('기존 데이터 삭제'))

        created = 0
        for code, name, protocol, target, endpoint in SEED:
            obj, is_new = Interface.objects.get_or_create(
                code=code,
                defaults={
                    'name': name, 'protocol': protocol,
                    'target_system': target, 'endpoint': endpoint,
                    'is_active': True,
                },
            )
            if is_new:
                created += 1

        self.stdout.write(self.style.SUCCESS(f'인터페이스 {created}건 신규 / 전체 {Interface.objects.count()}건'))

        interfaces = list(Interface.objects.all())
        now = timezone.now()
        log_count = 0
        for _ in range(opts['logs']):
            iface = random.choice(interfaces)
            success = random.random() > 0.08
            InterfaceLog.objects.create(
                interface=iface,
                status=InterfaceLog.Status.SUCCESS if success else InterfaceLog.Status.FAIL,
                latency_ms=random.randint(40, 2000) if success else None,
                request_summary=f'{iface.code} 호출',
                response_summary='200 OK' if success else '',
                error='' if success else 'Connection timeout',
            )
            log_count += 1

        # executed_at 분산 (auto_now_add이라 일괄 생성되므로 임의 조정)
        for i, log in enumerate(InterfaceLog.objects.order_by('-id')[:opts['logs']]):
            log.executed_at = now - timedelta(minutes=i * random.randint(1, 7))
            log.save(update_fields=['executed_at'])

        self.stdout.write(self.style.SUCCESS(f'로그 {log_count}건 생성'))
