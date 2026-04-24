import re

from django import forms

from .models import Interface


INPUT_CLS = (
    'w-full border border-slate-300 rounded px-3 py-2 text-sm '
    'focus:outline-none focus:ring-2 focus:ring-blue-500'
)


# 템플릿 하단 안내용 (상세 스키마는 구조화 필드로 대체됨)
PROTOCOL_CONFIG_HINTS = {
    'REST': 'method/headers/query_params/auth + timeout_sec',
    'SOAP': 'wsdl/operation + ws-security user/pass',
    'MQ':   'queue_manager/queue/channel (+ save_to_table for CONSUME_PROCESS)',
    'SFTP': 'host/port/user/remote_path/file_pattern',
    'BATCH': 'script/args + timeout_sec (schedule_cron 필수 권장)',
}


# 단순 cron 5필드 검증 — 각 필드: *, 숫자, a-b, */n, a-b/n, 쉼표 목록
_CRON_FIELD_RE = re.compile(r'^(\*|\d+|\d+-\d+|\*/\d+|\d+-\d+/\d+)(,(\*|\d+|\d+-\d+|\*/\d+|\d+-\d+/\d+))*$')
_CRON_RANGES = [(0, 59), (0, 23), (1, 31), (1, 12), (0, 7)]  # min, hour, dom, month, dow


def validate_cron(expr: str) -> None:
    parts = expr.split()
    if len(parts) != 5:
        raise forms.ValidationError('cron 식은 5개 필드여야 합니다 (분 시 일 월 요일)')
    for idx, (part, (lo, hi)) in enumerate(zip(parts, _CRON_RANGES)):
        if not _CRON_FIELD_RE.match(part):
            raise forms.ValidationError(f'{idx + 1}번째 필드 형식 오류: "{part}"')
        for num in re.findall(r'\d+', part):
            n = int(num)
            if n < lo or n > hi:
                raise forms.ValidationError(
                    f'{idx + 1}번째 필드 범위 초과: "{num}" (허용 {lo}~{hi})'
                )


def _kv_lines_to_dict(text: str, sep: str = ':') -> dict:
    """'key: value' 줄바꿈 입력 → dict. 빈 줄/주석(#) 무시."""
    out = {}
    for raw in (text or '').splitlines():
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        if sep not in line:
            raise forms.ValidationError(f'형식 오류: "{line}" (기대: key{sep} value)')
        k, v = line.split(sep, 1)
        out[k.strip()] = v.strip()
    return out


def _dict_to_kv_lines(d: dict, sep: str = ': ') -> str:
    return '\n'.join(f'{k}{sep}{v}' for k, v in (d or {}).items())


class InterfaceForm(forms.ModelForm):
    """인터페이스 등록/수정 — 프로토콜별 구조화 입력 (config_json 은 clean 에서 재조립)"""

    # REST
    rest_method = forms.ChoiceField(
        label='HTTP Method', required=False,
        choices=[('', '---'), ('GET', 'GET'), ('POST', 'POST'), ('PUT', 'PUT'), ('DELETE', 'DELETE')],
        widget=forms.Select(attrs={'class': INPUT_CLS}),
    )
    rest_auth_type = forms.ChoiceField(
        label='인증 방식', required=False,
        choices=[('', '없음'), ('bearer', 'Bearer'), ('basic', 'Basic'), ('api_key', 'API Key')],
        widget=forms.Select(attrs={'class': INPUT_CLS}),
    )
    rest_auth_token = forms.CharField(
        label='Token / API Key', required=False,
        widget=forms.TextInput(attrs={'class': INPUT_CLS, 'placeholder': 'bearer/api_key 일 때 사용'}),
    )
    rest_auth_user = forms.CharField(
        label='Auth User', required=False,
        widget=forms.TextInput(attrs={'class': INPUT_CLS, 'placeholder': 'basic 일 때 사용'}),
    )
    rest_auth_pass = forms.CharField(
        label='Auth Password', required=False,
        widget=forms.PasswordInput(render_value=True, attrs={'class': INPUT_CLS}),
    )
    rest_headers_text = forms.CharField(
        label='헤더 (줄바꿈 "key: value")', required=False,
        widget=forms.Textarea(attrs={
            'class': INPUT_CLS + ' font-mono text-xs', 'rows': 3,
            'placeholder': 'Accept: application/json\nX-Client-Id: svc-portal',
        }),
    )
    rest_query_params_text = forms.CharField(
        label='쿼리 파라미터 (줄바꿈 "key: value")', required=False,
        widget=forms.Textarea(attrs={
            'class': INPUT_CLS + ' font-mono text-xs', 'rows': 2,
            'placeholder': 'date: ${YYYYMMDD}',
        }),
    )
    rest_timeout_sec = forms.IntegerField(
        label='타임아웃 (초)', required=False, min_value=1, max_value=3600,
        widget=forms.NumberInput(attrs={'class': INPUT_CLS, 'placeholder': '30'}),
    )

    # SOAP
    soap_wsdl = forms.CharField(
        label='WSDL URL', required=False,
        widget=forms.TextInput(attrs={'class': INPUT_CLS, 'placeholder': 'https://partner.example.com/svc?wsdl'}),
    )
    soap_operation = forms.CharField(
        label='SOAP Operation', required=False,
        widget=forms.TextInput(attrs={'class': INPUT_CLS, 'placeholder': 'queryClaim'}),
    )
    soap_auth_user = forms.CharField(
        label='WS-Security User', required=False,
        widget=forms.TextInput(attrs={'class': INPUT_CLS, 'placeholder': 'svc'}),
    )
    soap_auth_pass = forms.CharField(
        label='WS-Security Password', required=False,
        widget=forms.PasswordInput(render_value=True, attrs={'class': INPUT_CLS}),
    )

    # MQ
    mq_queue_manager = forms.CharField(
        label='Queue Manager', required=False,
        widget=forms.TextInput(attrs={'class': INPUT_CLS, 'placeholder': 'QM_CORE'}),
    )
    mq_queue = forms.CharField(
        label='Queue', required=False,
        widget=forms.TextInput(attrs={'class': INPUT_CLS, 'placeholder': 'POLICY.SYNC.Q'}),
    )
    mq_channel = forms.CharField(
        label='Channel', required=False,
        widget=forms.TextInput(attrs={'class': INPUT_CLS, 'placeholder': 'SRV.APP.SVRCONN'}),
    )
    mq_save_to_table = forms.CharField(
        label='저장 테이블 (CONSUME_PROCESS)', required=False,
        widget=forms.TextInput(attrs={'class': INPUT_CLS, 'placeholder': 'policy_sync'}),
    )

    # SFTP
    sftp_host = forms.CharField(
        label='Host', required=False,
        widget=forms.TextInput(attrs={'class': INPUT_CLS, 'placeholder': 'sftp.example.com'}),
    )
    sftp_port = forms.IntegerField(
        label='Port', required=False, min_value=1, max_value=65535,
        widget=forms.NumberInput(attrs={'class': INPUT_CLS, 'placeholder': '22'}),
    )
    sftp_user = forms.CharField(
        label='User', required=False,
        widget=forms.TextInput(attrs={'class': INPUT_CLS, 'placeholder': 'acct'}),
    )
    sftp_remote_path = forms.CharField(
        label='원격 경로', required=False,
        widget=forms.TextInput(attrs={'class': INPUT_CLS, 'placeholder': '/inbound/'}),
    )
    sftp_file_pattern = forms.CharField(
        label='파일 패턴', required=False,
        widget=forms.TextInput(attrs={'class': INPUT_CLS, 'placeholder': '*.csv'}),
    )

    # BATCH
    batch_script = forms.CharField(
        label='스크립트 경로', required=False,
        widget=forms.TextInput(attrs={'class': INPUT_CLS, 'placeholder': '/opt/batch/bin/settle.sh'}),
    )
    batch_args_text = forms.CharField(
        label='인자 (줄바꿈/쉼표 구분)', required=False,
        widget=forms.Textarea(attrs={
            'class': INPUT_CLS + ' font-mono text-xs', 'rows': 2,
            'placeholder': '--date=${YYYYMMDD}',
        }),
    )
    batch_timeout_sec = forms.IntegerField(
        label='타임아웃 (초)', required=False, min_value=1, max_value=86400,
        widget=forms.NumberInput(attrs={'class': INPUT_CLS, 'placeholder': '3600'}),
    )

    class Meta:
        model = Interface
        fields = [
            'code', 'name', 'protocol', 'operation_type',
            'target_system', 'endpoint', 'schedule_cron', 'is_active',
        ]
        widgets = {
            'code': forms.TextInput(attrs={'class': INPUT_CLS, 'placeholder': 'IF_FSS_DAILY_REPORT'}),
            'name': forms.TextInput(attrs={'class': INPUT_CLS, 'placeholder': '금감원 일일 보고'}),
            'protocol': forms.Select(attrs={'class': INPUT_CLS, 'id': 'id_protocol'}),
            'operation_type': forms.Select(attrs={'class': INPUT_CLS, 'id': 'id_operation_type'}),
            'target_system': forms.TextInput(attrs={'class': INPUT_CLS, 'placeholder': '금감원'}),
            'endpoint': forms.TextInput(attrs={'class': INPUT_CLS, 'placeholder': 'https://api.fss.or.kr/...'}),
            'schedule_cron': forms.TextInput(attrs={'class': INPUT_CLS, 'placeholder': '0 2 * * *  (매일 새벽 2시)'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'w-4 h-4 text-blue-600'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['operation_type'].required = False
        if self.instance and self.instance.pk and self.instance.config_json:
            self._hydrate_from_config(self.instance.protocol, self.instance.config_json)

    def _hydrate_from_config(self, protocol: str, cfg: dict) -> None:
        auth = cfg.get('auth') or {}
        scalar: dict = {}
        if protocol == 'REST':
            scalar.update({
                'rest_method': cfg.get('method'),
                'rest_auth_type': auth.get('type'),
                'rest_auth_token': auth.get('token'),
                'rest_auth_user': auth.get('user'),
                'rest_auth_pass': auth.get('pass'),
                'rest_timeout_sec': cfg.get('timeout_sec'),
            })
        elif protocol == 'SOAP':
            scalar.update({
                'soap_wsdl': cfg.get('wsdl'),
                'soap_operation': cfg.get('operation'),
                'soap_auth_user': auth.get('user'),
                'soap_auth_pass': auth.get('pass'),
            })
        elif protocol == 'MQ':
            scalar.update({
                'mq_queue_manager': cfg.get('queue_manager'),
                'mq_queue': cfg.get('queue'),
                'mq_channel': cfg.get('channel'),
                'mq_save_to_table': cfg.get('save_to_table'),
            })
        elif protocol == 'SFTP':
            scalar.update({
                'sftp_host': cfg.get('host'),
                'sftp_port': cfg.get('port'),
                'sftp_user': cfg.get('user'),
                'sftp_remote_path': cfg.get('remote_path'),
                'sftp_file_pattern': cfg.get('file_pattern'),
            })
        elif protocol == 'BATCH':
            scalar.update({
                'batch_script': cfg.get('script'),
                'batch_timeout_sec': cfg.get('timeout_sec'),
            })
        for name, val in scalar.items():
            if val is not None and val != '':
                self.fields[name].initial = val

        if protocol == 'REST':
            if cfg.get('headers'):
                self.fields['rest_headers_text'].initial = _dict_to_kv_lines(cfg['headers'])
            if cfg.get('query_params'):
                self.fields['rest_query_params_text'].initial = _dict_to_kv_lines(cfg['query_params'])
        if protocol == 'BATCH' and cfg.get('args'):
            self.fields['batch_args_text'].initial = '\n'.join(str(a) for a in cfg['args'])

    def clean_schedule_cron(self):
        v = (self.cleaned_data.get('schedule_cron') or '').strip()
        if v:
            validate_cron(v)
        return v

    def clean(self):
        cleaned = super().clean()
        protocol = cleaned.get('protocol')
        op = cleaned.get('operation_type')
        if protocol and op:
            allowed = Interface.PROTOCOL_OPERATIONS.get(protocol, [])
            if op not in allowed:
                self.add_error(
                    'operation_type',
                    f'{protocol} 프로토콜에서는 {op} 오퍼레이션을 사용할 수 없습니다.',
                )

        # BATCH/SFTP 이외에는 schedule_cron 무시 (데이터 정합성)
        if protocol not in ('BATCH', 'SFTP'):
            cleaned['schedule_cron'] = ''

        self._config = self._build_config(cleaned, protocol)
        return cleaned

    def _build_config(self, cleaned: dict, protocol: str) -> dict:
        cfg: dict = {}

        def put(key, val):
            if val not in (None, '', []):
                cfg[key] = val

        if protocol == 'REST':
            put('method', cleaned.get('rest_method') or 'GET')
            headers = _kv_lines_to_dict(cleaned.get('rest_headers_text') or '')
            query_params = _kv_lines_to_dict(cleaned.get('rest_query_params_text') or '')
            put('headers', headers)
            put('query_params', query_params)
            put('timeout_sec', cleaned.get('rest_timeout_sec'))
            atype = cleaned.get('rest_auth_type')
            if atype:
                auth = {'type': atype}
                if atype in ('bearer', 'api_key') and cleaned.get('rest_auth_token'):
                    auth['token'] = cleaned['rest_auth_token']
                if atype == 'basic':
                    if cleaned.get('rest_auth_user'):
                        auth['user'] = cleaned['rest_auth_user']
                    if cleaned.get('rest_auth_pass'):
                        auth['pass'] = cleaned['rest_auth_pass']
                cfg['auth'] = auth

        elif protocol == 'SOAP':
            put('wsdl', cleaned.get('soap_wsdl'))
            put('operation', cleaned.get('soap_operation'))
            if cleaned.get('soap_auth_user') or cleaned.get('soap_auth_pass'):
                auth = {'type': 'ws-security'}
                if cleaned.get('soap_auth_user'):
                    auth['user'] = cleaned['soap_auth_user']
                if cleaned.get('soap_auth_pass'):
                    auth['pass'] = cleaned['soap_auth_pass']
                cfg['auth'] = auth

        elif protocol == 'MQ':
            missing = [
                self.fields[fn].label for fn in ('mq_queue_manager', 'mq_queue', 'mq_channel')
                if not cleaned.get(fn)
            ]
            if missing:
                raise forms.ValidationError(f'MQ 필수값 누락: {", ".join(missing)}')
            put('queue_manager', cleaned.get('mq_queue_manager'))
            put('queue', cleaned.get('mq_queue'))
            put('channel', cleaned.get('mq_channel'))
            put('save_to_table', cleaned.get('mq_save_to_table'))

        elif protocol == 'SFTP':
            missing = [
                self.fields[fn].label for fn in ('sftp_host', 'sftp_user', 'sftp_remote_path')
                if not cleaned.get(fn)
            ]
            if missing:
                raise forms.ValidationError(f'SFTP 필수값 누락: {", ".join(missing)}')
            put('host', cleaned.get('sftp_host'))
            put('port', cleaned.get('sftp_port') or 22)
            put('user', cleaned.get('sftp_user'))
            put('remote_path', cleaned.get('sftp_remote_path'))
            put('file_pattern', cleaned.get('sftp_file_pattern') or '*')

        elif protocol == 'BATCH':
            if not cleaned.get('batch_script'):
                raise forms.ValidationError('BATCH 필수값 누락: 스크립트 경로')
            put('script', cleaned.get('batch_script'))
            raw_args = (cleaned.get('batch_args_text') or '').strip()
            if raw_args:
                args = [x.strip() for x in raw_args.replace('\n', ',').split(',') if x.strip()]
                put('args', args)
            put('timeout_sec', cleaned.get('batch_timeout_sec') or 3600)

        return cfg

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.config_json = getattr(self, '_config', obj.config_json or {})
        if commit:
            obj.save()
        return obj
