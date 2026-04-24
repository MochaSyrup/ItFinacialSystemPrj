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
