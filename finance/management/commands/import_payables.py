import json
from pathlib import Path
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from finance.payable_import import import_payables

class Command(BaseCommand):
    help='Importa exportação normalizada de contas a pagar. Padrão: somente simulação.'
    def add_arguments(self,parser):
        parser.add_argument('file')
        parser.add_argument('--user',required=True)
        parser.add_argument('--apply',action='store_true')
    def handle(self,*args,**options):
        user=get_user_model().objects.get(username=options['user'],is_superuser=True,is_active=True)
        payload=json.loads(Path(options['file']).read_text(encoding='utf-8'))
        try: result=import_payables(payload,user,apply=options['apply'])
        except (ValueError,KeyError,TypeError) as exc: raise CommandError(str(exc))
        self.stdout.write(json.dumps(result,default=str,ensure_ascii=False))
