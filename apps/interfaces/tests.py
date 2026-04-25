from django.test import TestCase
from django.urls import reverse

from .forms import InterfaceForm, validate_cron
from .models import Interface, InterfaceLog
from .protocols import execute_interface
from .utils import mask_config


class CronValidationTests(TestCase):
    def test_valid_expressions(self):
        for expr in ['* * * * *', '0 2 * * *', '*/15 9-18 * * 1-5', '0,30 * 1,15 * *']:
            validate_cron(expr)  # should not raise

    def test_field_count_error(self):
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            validate_cron('0 2 * *')  # 4 fields

    def test_range_over_limit(self):
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            validate_cron('60 * * * *')  # minute > 59
        with self.assertRaises(ValidationError):
            validate_cron('* 24 * * *')  # hour > 23
        with self.assertRaises(ValidationError):
            validate_cron('* * 32 * *')  # dom > 31


class MaskConfigTests(TestCase):
    def test_masks_sensitive_keys_recursively(self):
        cfg = {
            'method': 'GET',
            'auth': {'type': 'bearer', 'token': 'secret-abc'},
            'headers': {'Accept': 'application/json'},
        }
        masked = mask_config(cfg)
        self.assertEqual(masked['method'], 'GET')
        self.assertEqual(masked['auth']['type'], 'bearer')
        self.assertEqual(masked['auth']['token'], '***')
        self.assertEqual(masked['headers']['Accept'], 'application/json')

    def test_empty_value_not_masked(self):
        self.assertEqual(mask_config({'password': ''}), {'password': ''})


class FormRoundTripTests(TestCase):
    """구조화 필드 → config_json 저장 → edit 진입 시 필드 역직렬화."""

    def _post_data(self, **overrides):
        base = {
            'code': 'IF_UNIT_REST', 'name': 'Unit REST',
            'protocol': 'REST', 'operation_type': 'REST_GET_QUERY',
            'target_system': 'TEST', 'endpoint': 'https://api.example.com/',
            'is_active': 'on',
            'rest_method': 'GET', 'rest_auth_type': 'bearer',
            'rest_auth_token': 'tok-123', 'rest_timeout_sec': '30',
            'rest_headers_text': 'Accept: application/json',
        }
        base.update(overrides)
        return base

    def test_rest_save_assembles_config_json(self):
        form = InterfaceForm(data=self._post_data())
        self.assertTrue(form.is_valid(), form.errors)
        obj = form.save()
        self.assertEqual(obj.config_json['method'], 'GET')
        self.assertEqual(obj.config_json['auth'], {'type': 'bearer', 'token': 'tok-123'})
        self.assertEqual(obj.config_json['headers'], {'Accept': 'application/json'})
        self.assertEqual(obj.config_json['timeout_sec'], 30)

    def test_edit_form_hydrates_from_config(self):
        form = InterfaceForm(data=self._post_data())
        form.is_valid()
        obj = form.save()

        edit = InterfaceForm(instance=obj)
        self.assertEqual(edit.fields['rest_method'].initial, 'GET')
        self.assertEqual(edit.fields['rest_auth_token'].initial, 'tok-123')
        self.assertEqual(edit.fields['rest_timeout_sec'].initial, 30)
        self.assertIn('Accept: application/json', edit.fields['rest_headers_text'].initial)

    def test_mq_missing_required_raises(self):
        data = self._post_data(
            code='IF_UNIT_MQ', protocol='MQ', operation_type='MQ_PUBLISH',
        )
        data['mq_queue_manager'] = 'QM1'
        form = InterfaceForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertTrue(any('MQ 필수값 누락' in err for err in form.non_field_errors()))

    def test_protocol_operation_whitelist(self):
        data = self._post_data(
            protocol='REST', operation_type='MQ_PUBLISH',
        )
        form = InterfaceForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn('operation_type', form.errors)

    def test_cron_cleared_for_non_batch_sftp(self):
        data = self._post_data(schedule_cron='0 2 * * *')
        form = InterfaceForm(data=data)
        self.assertTrue(form.is_valid(), form.errors)
        obj = form.save()
        self.assertEqual(obj.schedule_cron, '')

    def test_cron_validated_for_batch(self):
        data = {
            'code': 'IF_UNIT_BATCH', 'name': 'Unit BATCH',
            'protocol': 'BATCH', 'operation_type': 'BATCH_SCHEDULED',
            'endpoint': '/opt/x.sh', 'is_active': 'on',
            'schedule_cron': '60 2 * * *',
            'batch_script': '/opt/x.sh',
        }
        form = InterfaceForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn('schedule_cron', form.errors)


class ExecuteInterfaceTests(TestCase):
    def test_execute_creates_log(self):
        iface = Interface.objects.create(
            code='IF_X', name='X', protocol='REST', endpoint='https://x/',
        )
        log = execute_interface(iface)
        self.assertIsNotNone(log.pk)
        self.assertEqual(log.interface_id, iface.pk)
        self.assertIn(log.status, [InterfaceLog.Status.SUCCESS, InterfaceLog.Status.FAIL])


class LogRetryBulkTests(TestCase):
    def setUp(self):
        self.iface = Interface.objects.create(
            code='IF_Y', name='Y', protocol='REST', endpoint='https://y/',
        )
        for _ in range(3):
            InterfaceLog.objects.create(
                interface=self.iface, status=InterfaceLog.Status.FAIL,
                request_summary='req', error='boom',
            )

    def test_selected_bulk_retry_dedupes_same_interface(self):
        ids = list(InterfaceLog.objects.filter(status='FAIL').values_list('pk', flat=True))
        before = InterfaceLog.objects.count()
        resp = self.client.post(
            reverse('interfaces:log_retry_bulk'),
            data={'log_ids': [str(i) for i in ids]},
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        after = InterfaceLog.objects.count()
        # 3 건 선택했지만 모두 같은 iface → 1건만 새 로그 생성
        self.assertEqual(after - before, 1)

    def test_empty_selection_warns(self):
        resp = self.client.post(reverse('interfaces:log_retry_bulk'), data={}, follow=True)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '재처리할 로그를 선택하세요')

    def test_scope_all_processes_failed(self):
        before = InterfaceLog.objects.count()
        self.client.post(reverse('interfaces:log_retry_bulk'), data={'scope': 'all'})
        after = InterfaceLog.objects.count()
        self.assertEqual(after - before, 1)


class InterfaceDetailTests(TestCase):
    def test_detail_page_renders_and_masks(self):
        iface = Interface.objects.create(
            code='IF_DET', name='상세', protocol='REST',
            config_json={'method': 'GET', 'auth': {'type': 'bearer', 'token': 'super-secret'}},
        )
        resp = self.client.get(reverse('interfaces:detail', args=[iface.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'IF_DET')
        self.assertNotContains(resp, 'super-secret')
        self.assertContains(resp, '***')


class ListPaginationTests(TestCase):
    def test_pagination_limits_to_25(self):
        for i in range(30):
            Interface.objects.create(code=f'IF_{i:03d}', name=f'N{i}', protocol='REST')
        resp = self.client.get(reverse('interfaces:list'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '1 / 2')


class AdapterModeDispatchTests(TestCase):
    """live/mock 전환 로직 검증 — 실제 네트워크 호출 없이 dispatch 만 확인"""

    def test_per_interface_live_flag_overrides_settings(self):
        from apps.interfaces.protocols.base import ProtocolAdapter
        adapter = ProtocolAdapter(code='TEST')
        iface_mock = Interface(config_json={'live': False})
        iface_live = Interface(config_json={'live': True})
        # 전역이 꺼져 있어도 interface.live=True 면 live
        self.assertTrue(adapter._is_live(iface_live))
        self.assertFalse(adapter._is_live(iface_mock))

    def test_missing_lib_falls_back_to_mock_with_note(self):
        """_execute_live 가 AdapterLibraryMissing 을 던지면 mock 으로 폴백"""
        from apps.interfaces.protocols.base import AdapterLibraryMissing, ProtocolAdapter

        class _Broken(ProtocolAdapter):
            code = 'X'
            def _execute_live(self, interface):
                raise AdapterLibraryMissing('fake-lib 미설치')

        adapter = _Broken()
        iface = Interface.objects.create(
            code='IF_FB', name='fb', protocol='REST',
            config_json={'live': True},
        )
        result = adapter.execute(iface)
        # mock 으로 실행되었으므로 latency 가 잡혀 있음
        self.assertIsNotNone(result.latency_ms)
        # fallback 메모가 error 에 달려 있거나 비어 있음 (성공 케이스)
        if not result.success:
            self.assertIn('live 모드 fallback', result.error)

    def test_response_summary_truncated(self):
        """INTERFACE_RESPONSE_MAX_CHARS 초과분이 잘리는지"""
        from django.test import override_settings
        from apps.interfaces.protocols.base import ExecutionResult, ProtocolAdapter

        class _Bloated(ProtocolAdapter):
            code = 'Y'
            def _execute_mock(self, interface):
                return ExecutionResult(
                    success=True, latency_ms=10,
                    request_summary='req',
                    response_summary='A' * 8000,
                )

        iface = Interface.objects.create(code='IF_BIG', name='big', protocol='REST')
        with override_settings(INTERFACE_RESPONSE_MAX_CHARS=1000, INTERFACE_RETRY_MAX=0):
            result = _Bloated().execute(iface)
        self.assertLess(len(result.response_summary), 1200)
        self.assertIn('truncated', result.response_summary)


class CeleryDispatchTests(TestCase):
    """dispatch_interfaces 가 cron 매칭으로만 trigger 하는지"""

    def test_run_interface_skips_inactive(self):
        from apps.interfaces.tasks import run_interface
        iface = Interface.objects.create(
            code='IF_OFF', name='off', protocol='REST', is_active=False,
        )
        result = run_interface.run(iface.pk)
        self.assertTrue(result.get('skipped'))

    def test_run_interface_creates_log(self):
        from apps.interfaces.tasks import run_interface
        iface = Interface.objects.create(
            code='IF_ON', name='on', protocol='REST', is_active=True,
        )
        before = InterfaceLog.objects.count()
        run_interface.run(iface.pk)
        self.assertEqual(InterfaceLog.objects.count(), before + 1)

    def test_dispatch_skips_when_no_cron_matches(self):
        from apps.interfaces.tasks import dispatch_interfaces
        # 2099 년에만 도는 cron — 현재 분에 절대 안 걸림
        Interface.objects.create(
            code='IF_FUTURE', name='f', protocol='REST',
            is_active=True, schedule_cron='0 0 1 1 *',  # 매년 1월 1일 00:00
        )
        from datetime import datetime
        from unittest.mock import patch
        # 임의의 비매칭 시각 (3월 5일 14:23)
        fake_now = datetime(2026, 3, 5, 14, 23, 17)
        with patch('apps.interfaces.tasks.timezone.localtime', return_value=fake_now):
            result = dispatch_interfaces.run()
        # 매칭 안 됨 → dispatched 0
        self.assertEqual(result['dispatched'], 0)

    def test_dispatch_triggers_matching_cron(self):
        from apps.interfaces.tasks import dispatch_interfaces
        Interface.objects.create(
            code='IF_HIT', name='h', protocol='REST',
            is_active=True, schedule_cron='23 14 5 3 *',
        )
        from datetime import datetime
        from unittest.mock import patch
        fake_now = datetime(2026, 3, 5, 14, 23, 17)
        with patch('apps.interfaces.tasks.timezone.localtime', return_value=fake_now):
            result = dispatch_interfaces.run()
        self.assertEqual(result['dispatched'], 1)
        self.assertIn('IF_HIT', result['codes'])

    def test_cleanup_old_logs(self):
        from datetime import timedelta
        from django.utils import timezone
        from apps.interfaces.tasks import cleanup_old_logs
        iface = Interface.objects.create(code='IF_C', name='c', protocol='REST')
        old = InterfaceLog.objects.create(
            interface=iface, status=InterfaceLog.Status.SUCCESS, request_summary='r',
        )
        InterfaceLog.objects.filter(pk=old.pk).update(executed_at=timezone.now() - timedelta(days=120))
        InterfaceLog.objects.create(
            interface=iface, status=InterfaceLog.Status.SUCCESS, request_summary='r',
        )
        result = cleanup_old_logs.run(keep_days=90)
        self.assertEqual(result['deleted'], 1)
        self.assertEqual(InterfaceLog.objects.count(), 1)
