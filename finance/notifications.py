from datetime import timedelta
from urllib.parse import quote
import requests
from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from .models import NotificationSettings, NotificationLog, Entry
from .templatetags.finance_tags import money

def send_daily_summary():
    now=timezone.localtime()
    prefs=NotificationSettings.objects.filter(pk=1,enabled=True).first()
    if not prefs or now.hour<prefs.hour or not settings.EVOLUTION_KEY or not settings.EVOLUTION_INSTANCE: return
    # A unique daily claim prevents duplicate sends. Ambiguous delivery is never retried automatically.
    with transaction.atomic():
        log,created=NotificationLog.objects.get_or_create(date=now.date())
        if not created: return
    entries=Entry.objects.filter(cancelled=False,paid__lt=F('amount'),due__lte=now.date()+timedelta(days=prefs.days_before)).order_by('due','id')
    if not prefs.overdue: entries=entries.filter(due__gte=now.date())
    rows=list(entries)
    if not rows:
        log.status='Sem pendências';log.detail='Nenhuma conta no período configurado.';log.save();return
    lines=[f'*Financeiro GD • {now:%d/%m/%Y}*','Seus próximos compromissos:','']
    for entry in rows[:40]:
        label='Pagar' if entry.kind=='payable' else 'Receber'
        lines.append(f'{label}: {entry.title} | {money(entry.balance)} | {entry.due:%d/%m}'+(' • ATRASADA' if entry.due<now.date() else ''))
    if len(rows)>40: lines.append(f'+ {len(rows)-40} contas no painel.')
    lines+=['','https://financeiro.gdapps.online']
    try:
        result=requests.post(settings.EVOLUTION_URL.rstrip('/')+'/message/sendText/'+quote(settings.EVOLUTION_INSTANCE,safe=''),headers={'apikey':settings.EVOLUTION_KEY},json={'number':prefs.phone,'text':'\n'.join(lines)},timeout=30)
        if result.status_code in [200,201]: log.status='Enviado';log.detail=f'Resumo de {len(rows)} conta(s) aceito pela API.'
        else: log.status='Falha';log.detail=f'API retornou HTTP {result.status_code}. Verifique a integração.'
    except requests.RequestException:
        log.status='Verificar';log.detail='Não foi possível confirmar a entrega. Sem reenvio automático para evitar duplicidade.'
    log.save()
