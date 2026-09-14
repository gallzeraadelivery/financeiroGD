import requests
from urllib.parse import quote
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

class Command(BaseCommand):
    help='Consulta a conexão da instância sem enviar mensagens.'
    def handle(self,*args,**options):
        try:
            response=requests.get(settings.EVOLUTION_URL.rstrip('/')+'/instance/connectionState/'+quote(settings.EVOLUTION_INSTANCE,safe=''),headers={'apikey':settings.EVOLUTION_KEY},timeout=20)
        except requests.RequestException:
            raise CommandError('Não foi possível conectar com segurança à API. Verifique o endereço, certificado e disponibilidade.')
        if response.status_code!=200: raise CommandError(f'API respondeu HTTP {response.status_code}.')
        state=response.json().get('instance',{}).get('state')
        self.stdout.write(f'Instância {settings.EVOLUTION_INSTANCE}: {state}')
        if state!='open': raise CommandError('WhatsApp não está conectado.')
