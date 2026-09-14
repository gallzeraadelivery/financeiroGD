"""Transfers an instance-scoped credential between authorized hosts without printing it."""
import subprocess
from pathlib import Path
key=str(Path.home()/'.ssh'/'financeiro_gd_ed25519')
source='''import subprocess,json,urllib.request
c=json.loads(subprocess.check_output(['docker','inspect','evolution-api-5wzr-api-1']))[0]
env=dict(x.split('=',1) for x in c['Config']['Env'])
r=urllib.request.Request('http://127.0.0.1:32769/instance/fetchInstances',headers={'apikey':env['AUTHENTICATION_API_KEY']})
instances=json.load(urllib.request.urlopen(r,timeout=20))
instance=next(x for x in instances if x['name']=='principal')
token=instance.get('token')
if not token: raise RuntimeError('Token de instancia indisponivel')
print(token)
'''
secret=subprocess.run(['ssh','-i',key,'root@srv1653494.hstgr.cloud','python3 -'],input=source,text=True,capture_output=True,check=True).stdout.strip()
if not secret or '\n' in secret: raise RuntimeError('Invalid credential')
target='''from pathlib import Path
import json
p=Path('/opt/financeiro-gd/.env')
lines=[x for x in p.read_text().splitlines() if not x.startswith('EVOLUTION_KEY=')]
lines.append('EVOLUTION_KEY='+TOKEN)
p.write_text('\\n'.join(lines)+'\\n')
p.chmod(0o600)
'''.replace('TOKEN',repr(secret))
result=subprocess.run(['ssh','-i',key,'root@2.24.124.218','python3 -'],input=target,text=True,capture_output=True)
if result.returncode: raise RuntimeError('Unable to configure integration')
print('Credencial da instância principal configurada no financeiro, sem exposição.')
