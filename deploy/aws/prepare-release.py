"""Create a runtime-only bundle. BEKOO_ENV uses raw KEY=value lines, never shell syntax."""
import os
from pathlib import Path
import re
import shutil
import sys
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent


def parse_env(text):
    result = {}
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        key, sep, value = line.partition('=')
        if not sep or not re.fullmatch(r'[A-Z][A-Z0-9_]*', key) or key in result or '\x00' in value:
            raise ValueError('Invalid/duplicate KEY=value line in BEKOO_ENV (values hidden)')
        if value.startswith(('"', "'")):
            raise ValueError('Use raw values without surrounding quotes in BEKOO_ENV')
        result[key] = value
    return result


def validate(values):
    for key in ('DB_URL', 'DB_USER', 'DB_PASSWORD', 'REDIS_PASSWORD', 'ELASTIC_PASSWORD', 'JWT_SECRET', 'SPRING_COMMAND_URL', 'SPRING_QUERY_URL'):
        if not values.get(key) or values[key].startswith('REPLACE_'):
            raise ValueError(f'Missing real value: {key}')
    url = urlsplit(values['DB_URL'].removeprefix('jdbc:'))
    if (not values['DB_URL'].startswith('jdbc:mysql://') or url.hostname != 'bekoo.mysql.internal'
            or url.port not in (None, 3306) or url.path != '/booking_care_command' or url.username or url.password):
        raise ValueError('DB_URL must target native MySQL: bekoo.mysql.internal:3306/booking_care_command')
    if values['DB_USER'].lower() == 'root':
        raise ValueError('Use a dedicated MySQL application user')
    import base64
    try:
        if len(base64.b64decode(values['JWT_SECRET'], validate=True)) < 32:
            raise ValueError('short key')
    except Exception as exc:
        raise ValueError('JWT_SECRET must be Base64 of at least 32 random bytes') from exc
    if values.get('DB_DDL_AUTO', 'validate') not in ('validate', 'update'):
        raise ValueError('DB_DDL_AUTO must be validate or explicit bootstrap update')


def prepare(destination, text):
    values = parse_env(text)
    validate(values)
    destination.mkdir(mode=0o700, parents=True, exist_ok=False)
    for name in ('command', 'query', 'infra'):
        defaults = parse_env((ROOT / f'{name}.env.example').read_text())
        for key in defaults:
            lookup = f'SPRING_{name.upper()}_URL' if key == 'SPRING_URL' else key
            if lookup in values:
                defaults[key] = values[lookup]
            elif defaults[key].startswith('REPLACE_'):
                raise ValueError(f'Missing value: {lookup}')
        target = destination / f'{name}.env'
        target.write_text(''.join(f'{k}={v}\n' for k, v in defaults.items()))
        target.chmod(0o600)
    for name in ('compose.yaml', 'check-mysql.py'):
        shutil.copyfile(ROOT / name, destination / name)
    shutil.copyfile(ROOT / 'server/deploy.sh', destination / 'deploy.sh')


if __name__ == '__main__':
    try:
        prepare(Path(sys.argv[1]), os.environ.get('BEKOO_ENV', ''))
    except (ValueError, OSError) as exc:
        raise SystemExit(str(exc)) from None
