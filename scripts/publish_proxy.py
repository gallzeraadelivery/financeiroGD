import shutil, subprocess, sys
from pathlib import Path
from datetime import datetime
path=Path('/opt/edge/nginx/active.conf')
stage=sys.argv[1]
original=path.read_text()
if stage=='http':
    marker='# financeiro-gd http'
    block='''
# financeiro-gd http
server {
    listen 80;
    server_name financeiro.gdapps.online;
    location /.well-known/acme-challenge/ { root /var/www/certbot; }
    location / { return 301 https://$host$request_uri; }
}
'''
else:
    marker='# financeiro-gd https'
    block='''
# financeiro-gd https
server {
    listen 443 ssl;
    http2 on;
    server_name financeiro.gdapps.online;
    ssl_certificate /etc/letsencrypt/live/financeiro.gdapps.online/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/financeiro.gdapps.online/privkey.pem;
    client_max_body_size 1m;
    location / {
        resolver 127.0.0.11 valid=30s;
        set $financeiro_backend financeiro-gd-web;
        proxy_pass http://$financeiro_backend:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-For $remote_addr;
    }
}
'''
if marker not in original:
    shutil.copy2(path,path.with_name('active.conf.financeiro-backup-'+datetime.now().strftime('%Y%m%d%H%M%S')))
    path.write_text(original+block)
    check=subprocess.run(['docker','exec','edge-nginx','nginx','-t'])
    if check.returncode:
        path.write_text(original)
        raise SystemExit('Configuração rejeitada e restaurada.')
    subprocess.run(['docker','exec','edge-nginx','nginx','-s','reload'],check=True)
print('Proxy financeiro configurado: '+stage)
