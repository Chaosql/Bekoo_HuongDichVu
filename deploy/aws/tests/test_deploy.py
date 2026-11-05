"""Run the actual deploy script against fake Docker and HTTP endpoints."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'server/deploy.sh'
OLD, NEW = 'a' * 40, 'b' * 40
FAKE = r'''#!/usr/bin/env python3
import json, os, pathlib, sys
p = pathlib.Path(os.environ['STATE'])
s = json.loads(p.read_text())
a = sys.argv[1:]
name = pathlib.Path(sys.argv[0]).name
if name == 'sleep': sys.exit(0)
if name == 'aws':
    print('fake-token'); sys.exit(0)
if a[:2] == ['network', 'inspect']:
    print(json.dumps([{'Driver':'bridge','IPAM':{'Config':[{'Subnet':'172.30.83.0/24','Gateway':'172.30.83.1'}]}}])); sys.exit(0)
if a[0] == 'login': sys.stdin.read(); sys.exit(0)
if a[0] == 'run': sys.exit(1 if s.get('db_failure') else 0)
if name == 'curl':
    print('{"status":"DOWN"}' if s.get('unhealthy') and s['running'].get('query') == 'b'*40 else '{"status":"UP"}')
    sys.exit(0)
if a[0] == 'compose':
    assert 'IMAGE_TAG' not in os.environ and 'IMAGE_PREFIX' not in os.environ
s['calls'].append(a)
p.write_text(json.dumps(s))
if a[0] == 'compose':
    a = a[a.index('-f')+2:]
    if a[:2] == ['ps','-q']:
        if s['running'].get(a[2]): print(a[2])
    elif a[0] == 'up':
        if 'command' in a:
            tag = next(x.split('=',1)[1] for x in pathlib.Path('release.env').read_text().splitlines() if x.startswith('IMAGE_TAG='))
            s['running'] = dict(command=tag, query=tag)
            p.write_text(json.dumps(s))
        elif s.get('infra_failure'): sys.exit(1)
elif a[0] == 'pull':
    if s.get('pull_failure') and 'bekoo-query:' in a[-1]: sys.exit(1)
elif a[0] == 'inspect':
    tag = s['running'][a[-1]]
    if s.get('wrong_image') and a[-1] == 'query' and tag == 'b'*40: tag = 'c'*40
    print(a[-1] + ':' + tag)
elif a[:2] == ['image', 'inspect']:
    ref = a[-1]
    service = 'query' if 'query' in ref else 'command'
    tag = ref.rsplit(':',1)[-1]
    if '-f' in a:
        if '.Id' in a[a.index('-f')+1]: print(service + ':' + tag)
        else: print('c'*40 if s.get('bad_label') and tag == 'b'*40 else tag)
'''

class DeploymentTests(unittest.TestCase):
    def deploy(self, **changes):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            app = base / 'bekoo'
            app.mkdir()
            (app / 'compose.yaml').touch()
            (app / 'release.env').write_text(f'IMAGE_PREFIX=123456789012.dkr.ecr.ap-southeast-1.amazonaws.com\nIMAGE_TAG={OLD}\nCOMMAND_HOST_PORT=8083\nQUERY_HOST_PORT=8084\n')
            state = dict(running=dict(command=OLD, query=OLD), calls=[])
            state.update(changes)
            path = base / 'state.json'
            path.write_text(json.dumps(state))
            (app / 'check-mysql.py').write_text((SCRIPT.parents[1] / 'check-mysql.py').read_text())
            (app / 'command.env').write_text('DB_URL=jdbc:mysql://bekoo.mysql.internal:3306/booking_care_command\nDB_USER=bekoo\nDB_PASSWORD=test-secret\n')
            for tool in ['docker', 'curl', 'sleep', 'aws']:
                exe = base / tool
                exe.write_text(FAKE)
                exe.chmod(0o755)
            env = dict(os.environ, PATH=f'{base}:{os.environ["PATH"]}', STATE=str(path), APPS_ROOT=tmp,
                       IMAGE_TAG='stale-shell-tag', IMAGE_PREFIX='stale-shell-prefix')
            result = subprocess.run(['bash', str(SCRIPT), 'bekoo', NEW], env=env, capture_output=True, text=True, timeout=45)
            return result, json.loads(path.read_text()), (app / 'release.env').read_text()

    def test_first_deploy(self):
        result, state, release = self.deploy(running={})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(state['running'], dict(command=NEW, query=NEW))
        self.assertIn(NEW, release)

    def test_same_sha_recreates_to_apply_runtime_env(self):
        result, state, release = self.deploy(running=dict(command=NEW, query=NEW))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(any('up' in c for c in state['calls']))
        self.assertIn(NEW, release)

    def test_health_failure_rolls_back_both(self):
        result, state, release = self.deploy(unhealthy=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(state['running'], dict(command=OLD, query=OLD))
        self.assertIn(OLD, release)
        self.assertIn('Rollback healthy', result.stderr)

    def test_pull_failure_preserves_release(self):
        result, state, release = self.deploy(pull_failure=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(state['running'], dict(command=OLD, query=OLD))
        self.assertIn(OLD, release)

    def test_revision_mismatch_preserves_release(self):
        result, state, release = self.deploy(bad_label=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(state['running'], dict(command=OLD, query=OLD))
        self.assertIn(OLD, release)

    def test_infrastructure_failure_preserves_release(self):
        result, state, release = self.deploy(infra_failure=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(state['running'], dict(command=OLD, query=OLD))
        self.assertIn(OLD, release)

    def test_wrong_running_image_rolls_back_both(self):
        result, state, release = self.deploy(wrong_image=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(state['running'], dict(command=OLD, query=OLD))
        self.assertIn(OLD, release)
        self.assertIn('Rollback healthy', result.stderr)

    def test_database_failure_preserves_running_release(self):
        result, state, release = self.deploy(db_failure=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(state['running'], dict(command=OLD, query=OLD))
        self.assertIn(OLD, release)

    def test_first_deploy_unhealthy_reports_manual_recovery(self):
        result, state, release = self.deploy(running={}, unhealthy=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Manual recovery required', result.stderr)

if __name__ == '__main__':
    unittest.main()
