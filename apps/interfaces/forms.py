import json

from django import forms

from .models import Interface


INPUT_CLS = (
    'w-full border border-slate-300 rounded px-3 py-2 text-sm '
    'focus:outline-none focus:ring-2 focus:ring-blue-500'
)


PROTOCOL_CONFIG_HINTS = {
    'REST': (
        '{\n'
        '  "method": "GET",\n'
        '  "headers": {"Accept": "application/json"},\n'
        '  "auth": {"type": "bearer", "token": "xxxx"},\n'
        '  "query_params": {"date": "${YYYYMMDD}"},\n'
        '  "timeout_sec": 30\n'
        '}'
    ),
    'SOAP': (
        '{\n'
        '  "wsdl": "https://partner.example.com/ws/Svc?wsdl",\n'
        '  "operation": "queryClaim",\n'
        '  "auth": {"type": "ws-security", "user": "svc", "pass": "xxxx"}\n'
        '}'
    ),
    'MQ': (
        '{\n'
        '  "queue_manager": "QM_CORE",\n'
        '  "queue": "POLICY.SYNC.Q",\n'
        '  "channel": "SRV.APP.SVRCONN",\n'
        '  "save_to_table": "policy_sync",\n'
        '  "auth": {"user": "mqsvc", "pass": "xxxx"}\n'
        '}'
    ),
    'SFTP': (
        '{\n'
        '  "host": "sftp.example.com",\n'
        '  "port": 22,\n'
        '  "user": "acct",\n'
        '  "auth": "key",\n'
        '  "key_path": "/keys/id_rsa",\n'
        '  "remote_path": "/inbound/",\n'
        '  "file_pattern": "*.csv"\n'
        '}'
    ),
    'BATCH': (
        '{\n'
        '  "script": "/opt/batch/bin/settle.sh",\n'
        '  "args": ["--date=${YYYYMMDD}"],\n'
        '  "timeout_sec": 3600\n'
        '}'
    ),
}


class InterfaceForm(forms.ModelForm):
    config_json_text = forms.CharField(
        label='프로토콜 설정 (JSON)',
        required=False,
        widget=forms.Textarea(attrs={
            'class': INPUT_CLS + ' font-mono text-xs',
            'rows': 8,
            'placeholder': '{}',
        }),
        help_text='프로토콜별 호출 파라미터(인증·헤더·호스트 등)를 JSON 으로 입력합니다.',
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
            self.fields['config_json_text'].initial = json.dumps(
                self.instance.config_json, ensure_ascii=False, indent=2
            )

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
        # BATCH 이면 schedule_cron 권장 (비어도 허용하되 경고 없음)
        return cleaned

    def clean_config_json_text(self):
        raw = self.cleaned_data.get('config_json_text', '').strip()
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError as e:
            raise forms.ValidationError(f'JSON 파싱 실패: {e}')

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.config_json = self.cleaned_data.get('config_json_text') or {}
        if commit:
            obj.save()
        return obj
