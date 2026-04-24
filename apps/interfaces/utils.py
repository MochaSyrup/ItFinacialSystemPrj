SENSITIVE_KEYS = {'token', 'pass', 'password', 'secret', 'api_key', 'apikey'}


def mask_config(value):
    """config_json 을 재귀 순회하여 민감 키 값을 '***' 로 치환."""
    if isinstance(value, dict):
        return {k: ('***' if k.lower() in SENSITIVE_KEYS and v else mask_config(v))
                for k, v in value.items()}
    if isinstance(value, list):
        return [mask_config(x) for x in value]
    return value
