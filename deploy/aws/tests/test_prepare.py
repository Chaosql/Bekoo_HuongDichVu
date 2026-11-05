import base64
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('prepare', ROOT / 'prepare-release.py')
prepare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare)


def config():
    values = prepare.parse_env((ROOT / 'env.aws.example').read_text())
    for k, v in values.items():
        if v.startswith('REPLACE_'):
            values[k] = 'test$literal-secret'
    values['JWT_SECRET'] = base64.b64encode(bytes(48)).decode()
    return values


class PreparationTests(unittest.TestCase):
    def test_bundle_splits_secrets_without_shell_interpolation(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / 'release'
            prepare.prepare(dest, ''.join(f'{k}={v}\n' for k, v in config().items()))
            self.assertIn('DB_PASSWORD=test$literal-secret\n', (dest / 'command.env').read_text())
            self.assertNotIn('DB_PASSWORD', (dest / 'query.env').read_text())
            self.assertNotIn('JWT_SECRET', (dest / 'infra.env').read_text())
            self.assertEqual((dest / 'command.env').stat().st_mode & 0o777, 0o600)
            self.assertIn('SPRING_URL=https://bekoo-query.chiikaiwa.me', (dest / 'query.env').read_text())
            self.assertFalse(any(dest.rglob('*.java')))

    def test_root_and_remote_database_are_rejected(self):
        for key, value in [('DB_USER', 'root'), ('DB_URL', 'jdbc:mysql://public.example.com:3306/booking_care_command')]:
            with self.subTest(key=key):
                values = config()
                values[key] = value
                with self.assertRaises(ValueError):
                    prepare.validate(values)

    def test_duplicate_and_shell_quoted_values_are_rejected(self):
        for text in ['DB_USER=a\nDB_USER=b', "DB_PASSWORD='secret'", 'export DB_USER=a']:
            with self.subTest(text=text), self.assertRaises(ValueError):
                prepare.parse_env(text)

    def test_infrastructure_change_is_rejected_before_env_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            incoming = root / 'incoming' / ('b' * 40)
            runtime = root / 'runtime'
            incoming.mkdir(parents=True)
            runtime.mkdir()
            for name in ['compose.yaml', 'check-mysql.py', 'deploy.sh', 'command.env', 'query.env', 'infra.env']:
                (incoming / name).write_text('incoming')
            (runtime / 'infra.env').write_text('existing secret')
            (runtime / 'command.env').write_text('existing app env')
            result = subprocess.run(['bash', str(ROOT / 'server/activate-release.sh'), 'b' * 40,
                                     '123456789012.dkr.ecr.ap-southeast-1.amazonaws.com'],
                                    env=dict(os.environ, BEKOO_ROOT=tmp), capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual((runtime / 'command.env').read_text(), 'existing app env')
            self.assertNotIn('existing secret', result.stderr)

class ActivationTests(unittest.TestCase):
    def test_failed_release_restores_previous_env_and_both_images(self):
        from test_deploy import FAKE, OLD, NEW
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime = root / 'runtime'
            runtime.mkdir()
            values = config()
            payload = ''.join(f'{k}={v}\n' for k, v in values.items())
            incoming = root / 'incoming' / NEW
            prepare.prepare(incoming, payload)
            for name in ['compose.yaml', 'infra.env', 'query.env']:
                (runtime / name).write_bytes((incoming / name).read_bytes())
            old_command = (incoming / 'command.env').read_text().replace('DB_PASSWORD=test$literal-secret', 'DB_PASSWORD=previous-secret')
            (runtime / 'command.env').write_text(old_command)
            registry = '123456789012.dkr.ecr.ap-southeast-1.amazonaws.com'
            (runtime / 'release.env').write_text(f'IMAGE_PREFIX={registry}\nIMAGE_TAG={OLD}\nCOMMAND_HOST_PORT=8083\nQUERY_HOST_PORT=8084\n')
            import json
            statefile = root / 'state.json'
            statefile.write_text(json.dumps(dict(running=dict(command=OLD, query=OLD), calls=[], unhealthy=True)))
            for tool in ['docker', 'aws', 'curl', 'sleep']:
                exe = root / tool
                exe.write_text(FAKE)
                exe.chmod(0o755)
            env = dict(os.environ, PATH=f'{root}:{os.environ["PATH"]}', STATE=str(statefile), BEKOO_ROOT=tmp)
            result = subprocess.run(['bash', str(ROOT / 'server/activate-release.sh'), NEW, registry],
                                    env=env, capture_output=True, text=True, timeout=45)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual((runtime / 'command.env').read_text(), old_command)
            self.assertEqual(json.loads(statefile.read_text())['running'], dict(command=OLD, query=OLD))
            self.assertNotIn('previous-secret', result.stdout + result.stderr)
            self.assertIn('Rollback healthy', result.stderr)


if __name__ == '__main__':
    unittest.main()
