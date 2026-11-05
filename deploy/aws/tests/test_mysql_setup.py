"""Run AL2023 provisioning with a disposable filesystem and fake service/package tools."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
FAKE = r'''#!/usr/bin/env python3
import json, os, pathlib, sys
p=pathlib.Path(os.environ['MYSQL_TEST_STATE'])
s=json.loads(p.read_text()); name=pathlib.Path(sys.argv[0]).name; args=sys.argv[1:]
s['calls'].append([name]+args); p.write_text(json.dumps(s))
if name=='id': print(0)
elif name=='uname': print('x86_64')
elif name=='rpm': sys.exit(0 if s['installed'] else 1)
elif name=='mysqld':
    if '--version' in args: print('mysqld Ver 8.4.13 for Linux on x86_64 (MySQL Community Server - GPL)')
    elif s.get('invalid_config'): sys.exit(1)
elif name=='systemctl' and args[0]=='is-active': sys.exit(0 if s['running'] else 3)
elif name=='systemctl' and args[0]=='restart':
    s['running']=True; p.write_text(json.dumps(s))
'''

class MySQLProvisionTests(unittest.TestCase):
    def provision(self, mode='--configure-existing', **changes):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); fs=root/'fs'; server=root/'server'; server.mkdir(); binary=root/'bin'; binary.mkdir()
            for d in ['etc/my.cnf.d','etc/systemd/system','etc/yum.repos.d','var/lib/mysql','opt']:
                (fs/d).mkdir(parents=True,exist_ok=True)
            (fs/'etc/os-release').write_text('ID=amzn\nVERSION_ID=2023\n')
            (fs/'etc/my.cnf').write_text('[mysqld]\ndatadir=/var/lib/mysql\n')
            (fs/'var/lib/mysql/user-data').write_text('preserve this data')
            state=dict(installed=True,running=False,calls=[]); state.update(changes)
            statefile=root/'state.json'; statefile.write_text(json.dumps(state))
            for name in ['id','uname','rpm','mysqld','systemctl','dnf','docker']:
                p=binary/name; p.write_text(FAKE); p.chmod(0o755)
            (server/'setup-network.sh').write_text('#!/bin/bash\nexit 0\n')
            (root/'mysql-demo.cnf').write_bytes((ROOT/'mysql-demo.cnf').read_bytes())
            source=(ROOT/'server/setup-mysql-ec2.sh').read_text()
            # Remap absolute host paths before execution; never mutate the test host.
            for prefix in ['/etc','/var/lib/mysql','/opt/bekoo','/usr/sbin/mysqld']:
                source=source.replace(prefix,str(fs)+prefix)
            script=server/'setup-mysql-ec2.sh'; script.write_text(source)
            result=subprocess.run(['bash',str(script),mode],capture_output=True,text=True,
                                  env=dict(os.environ,PATH=f'{binary}:{os.environ["PATH"]}',MYSQL_TEST_STATE=str(statefile)),timeout=10)
            files={str(p.relative_to(fs)):p.read_text() for p in fs.rglob('*') if p.is_file()}
            return result,json.loads(statefile.read_text()),files

    def test_existing_package_is_configured_without_installing_or_touching_data(self):
        result,state,files=self.provision()
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertFalse(any(c[0]=='dnf' for c in state['calls']))
        self.assertEqual(files['var/lib/mysql/user-data'],'preserve this data')
        self.assertIn('max_connections=20',files['etc/my.cnf.d/bekoo.cnf'])
        self.assertIn('!include',files['etc/my.cnf'])
        self.assertIn('ExecStartPre=+/bin/bash',files['etc/systemd/system/mysqld.service.d/bekoo-network.conf'])
        self.assertTrue(state['running'])

    def test_running_unmanaged_database_is_not_changed(self):
        result,state,files=self.provision(running=True)
        self.assertNotEqual(result.returncode,0)
        self.assertNotIn('etc/my.cnf.d/bekoo.cnf',files)
        self.assertFalse(any(c[:2]==['systemctl','restart'] for c in state['calls']))

    def test_install_fresh_refuses_existing_package(self):
        result,state,files=self.provision(mode='--install-fresh')
        self.assertNotEqual(result.returncode,0)
        self.assertFalse(any(c[0]=='dnf' for c in state['calls']))
        self.assertNotIn('etc/my.cnf.d/bekoo.cnf',files)

    def test_invalid_configuration_never_starts_database(self):
        result,state,files=self.provision(invalid_config=True)
        self.assertNotEqual(result.returncode,0)
        self.assertFalse(state['running'])
        self.assertNotIn('etc/my.cnf.d/bekoo.cnf',files)
        self.assertNotIn('!include',files['etc/my.cnf'])
        self.assertFalse(any(c[:2]==['systemctl','restart'] for c in state['calls']))

if __name__=='__main__': unittest.main()
