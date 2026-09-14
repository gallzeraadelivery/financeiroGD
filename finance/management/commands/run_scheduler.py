import time
import logging
from django.core.management.base import BaseCommand
from django.db import close_old_connections
from finance.services import generate_recurrences
from finance.notifications import send_daily_summary

class Command(BaseCommand):
    def add_arguments(self,parser): parser.add_argument('--once',action='store_true')
    def handle(self,*args,**options):
        while True:
            try:
                close_old_connections()
                generate_recurrences()
                send_daily_summary()
            except Exception:
                logging.exception('Falha no agendador financeiro')
            if options['once']: return
            time.sleep(60)
