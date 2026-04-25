#!/usr/bin/env bash
set -euo pipefail

cmd="${1:-web}"

# DB 가 뜰 때까지 대기 (postgres 만 해당)
if [ -n "${POSTGRES_HOST:-}" ]; then
    echo "▶ waiting for postgres at ${POSTGRES_HOST}:${POSTGRES_PORT:-5432}..."
    python - <<'PY'
import os, socket, time, sys
host = os.environ['POSTGRES_HOST']
port = int(os.environ.get('POSTGRES_PORT', '5432'))
deadline = time.time() + 60
while time.time() < deadline:
    try:
        with socket.create_connection((host, port), timeout=2):
            print('✓ postgres reachable')
            sys.exit(0)
    except OSError:
        time.sleep(1)
print('✗ postgres unreachable', file=sys.stderr)
sys.exit(1)
PY
fi

case "$cmd" in
    web)
        echo "▶ migrate"
        python manage.py migrate --noinput
        echo "▶ collectstatic"
        python manage.py collectstatic --noinput
        echo "▶ gunicorn"
        exec gunicorn portal.wsgi:application \
            --bind 0.0.0.0:8000 \
            --workers "${GUNICORN_WORKERS:-3}" \
            --access-logfile - \
            --error-logfile -
        ;;
    worker)
        exec celery -A portal worker -l info
        ;;
    beat)
        # beat 가 db 마이그레이션 전에 뜨면 안 됨 — web 컨테이너가 먼저 migrate 끝낸 뒤 시작되도록 compose 에서 depends_on 으로 묶음
        exec celery -A portal beat -l info
        ;;
    manage)
        shift
        exec python manage.py "$@"
        ;;
    shell)
        exec bash
        ;;
    *)
        exec "$@"
        ;;
esac
