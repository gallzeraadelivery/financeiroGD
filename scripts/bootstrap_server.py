import os
import secrets
from pathlib import Path
root=Path('/opt/financeiro-gd')
root.mkdir(mode=0o750,exist_ok=True)
env=root/'.env'
if not env.exists():
    env.write_text('\n'.join(['DEBUG=0','SECRET_KEY='+secrets.token_urlsafe(64),'ALLOWED_HOSTS=financeiro.gdapps.online,localhost,127.0.0.1','POSTGRES_HOST=db','POSTGRES_DB=financeiro','POSTGRES_USER=financeiro','POSTGRES_PASSWORD='+secrets.token_urlsafe(40),'EVOLUTION_URL=https://evolution-api-5wzr.srv1653494.hstgr.cloud','EVOLUTION_INSTANCE=principal','']))
    env.chmod(0o600)
print('Ambiente financeiro preparado.')
