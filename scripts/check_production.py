import subprocess
from pathlib import Path
root=Path('/opt/financeiro-gd')
backup=max((root/'backups').glob('*.dump'),key=lambda p:p.stat().st_mtime)
with backup.open('rb') as stream:
    check=subprocess.run(['docker','compose','exec','-T','db','pg_restore','--list'],cwd=root,stdin=stream,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
if check.returncode: raise SystemExit('Backup inválido.')
print('Backup PostgreSQL legível e não vazio.')
cron=subprocess.run(['crontab','-l'],capture_output=True,text=True)
renew=any('/opt/edge/renew.sh' in line and not line.lstrip().startswith('#') for line in cron.stdout.splitlines())
print('Renovação existente no crontab: '+str(renew))
print(subprocess.check_output(['docker','compose','ps','--format','{{.Name}} {{.State}}'],cwd=root,text=True).strip())
