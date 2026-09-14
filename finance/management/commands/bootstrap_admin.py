import secrets
from pathlib import Path
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from finance.models import NotificationSettings

class Command(BaseCommand):
    def add_arguments(self,parser): parser.add_argument('--password-file',required=True)
    def handle(self,*args,**options):
        email='dimmygalvan@gmail.com'
        if not get_user_model().objects.filter(username=email).exists():
            password=secrets.token_urlsafe(18)
            get_user_model().objects.create_superuser(email,email,password,first_name='Dimym')
            target=Path(options['password_file']);target.write_text(password);target.chmod(0o600)
            self.stdout.write('Administrador criado; senha salva no arquivo privado informado.')
        else: self.stdout.write('Administrador já existente; senha preservada.')
        NotificationSettings.objects.get_or_create(pk=1,defaults={'phone':'5565998040550','enabled':True,'hour':8})
