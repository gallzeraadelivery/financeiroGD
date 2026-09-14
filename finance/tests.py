import uuid
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch, Mock
from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.utils import timezone
from .models import Entry, Contact, Product, Recurrence, NotificationSettings, NotificationLog, Payment
from .services import add_months, create_sale, generate_recurrences, settle
from .notifications import send_daily_summary

@override_settings(SECURE_SSL_REDIRECT=False,STORAGES={'default':{'BACKEND':'django.core.files.storage.FileSystemStorage'},'staticfiles':{'BACKEND':'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class FinanceTests(TestCase):
    def setUp(self):
        self.admin=get_user_model().objects.create_superuser('admin@example.com','admin@example.com','A-strong-test-password-123')
        self.contact=Contact.objects.create(name='Cliente teste',kind='customer')
        self.product=Product.objects.create(name='Produto teste',price='100.00')

    def test_month_end_keeps_anchor(self):
        self.assertEqual(add_months(date(2026,1,31),1),date(2026,2,28))
        self.assertEqual(add_months(date(2026,1,31),2),date(2026,3,31))
        self.assertEqual(add_months(date(2024,1,31),1),date(2024,2,29))

    def test_sales_registration_without_receivable_access(self):
        seller=get_user_model().objects.create_user('seller@example.com',password='test')
        seller.user_permissions.add(*Permission.objects.filter(content_type__app_label='finance',codename__in=['view_sales','add_sales','view_payable']))
        self.client.force_login(seller)
        self.assertContains(self.client.get('/vendas/'),'Nova venda')
        self.assertEqual(self.client.get('/vendas/nova/').status_code,200)
        result=self.client.post('/vendas/nova/',{'contact':self.contact.pk,'product':self.product.pk,'quantity':1,'unit_price':'100.00','installments':2,'first_due':timezone.localdate().isoformat()})
        self.assertEqual(result.status_code,302)
        installments=Entry.objects.filter(kind='receivable')
        self.assertEqual(installments.count(),2)
        self.assertEqual(sum(e.amount for e in installments),Decimal('100.00'))
        entry=installments.first()
        for url in ['/contas/receivable/','/contas/receivable/nova/',f'/conta/{entry.pk}/',f'/conta/{entry.pk}/baixa/','/lembretes/']:
            self.assertEqual(self.client.get(url).status_code,403,url)
        for url in [f'/conta/{entry.pk}/baixa/',f'/conta/{entry.pk}/cancelar/',f'/vendas/{entry.sale_id}/cancelar/']:
            self.assertEqual(self.client.post(url,{}).status_code,403,url)
        dashboard=self.client.get('/')
        self.assertNotContains(dashboard,'A receber no mês')
        self.assertNotContains(dashboard,'Saldo previsto no mês')
        self.assertNotContains(dashboard,'Produto teste')
        self.assertFalse(seller.has_perm('finance.view_receivable'))

    def test_installments_sum_exactly(self):
        sale=create_sale({'contact':self.contact,'product':self.product,'quantity':1,'unit_price':Decimal('100.00'),'installments':3,'first_due':date(2026,1,31)},self.admin)
        entries=list(Entry.objects.filter(sale=sale))
        self.assertEqual([e.amount for e in entries],[Decimal('33.34'),Decimal('33.33'),Decimal('33.33')])
        self.assertEqual(sum(e.amount for e in entries),sale.total)
        self.assertEqual(entries[2].due,date(2026,3,31))

    def test_recurrence_is_idempotent_and_honors_end(self):
        rule=Recurrence.objects.create(kind='payable',title='Aluguel',amount=100,start=date(2026,1,31),end=date(2026,3,31))
        generate_recurrences(date(2026,12,31));generate_recurrences(date(2026,12,31))
        self.assertEqual(Entry.objects.filter(recurrence=rule).count(),3)

    def test_partial_payment_double_submit_and_overpayment(self):
        entry=Entry.objects.create(kind='payable',title='Teste',amount=100,due=timezone.localdate())
        token=uuid.uuid4()
        self.assertTrue(settle(entry.pk,Decimal(40),timezone.localdate(),'',self.admin,token))
        self.assertFalse(settle(entry.pk,Decimal(40),timezone.localdate(),'',self.admin,token))
        with self.assertRaises(ValueError):settle(entry.pk,Decimal(61),timezone.localdate(),'',self.admin,uuid.uuid4())
        entry.refresh_from_db();self.assertEqual(entry.balance,Decimal(60))
        self.assertEqual(Payment.objects.count(),1)

    def test_permissions_apply_to_direct_urls_and_dashboard(self):
        user=get_user_model().objects.create_user('viewer@example.com',password='test')
        user.user_permissions.add(Permission.objects.get(codename='view_receivable',content_type__app_label='finance'))
        entry=Entry.objects.create(kind='payable',title='Despesa confidencial',amount=900,due=timezone.localdate())
        self.client.force_login(user)
        for url in ['/contas/payable/',f'/conta/{entry.pk}/','/usuarios/','/lembretes/','/contas/receivable/nova/','/vendas/nova/']:
            self.assertEqual(self.client.get(url).status_code,403,url)
        self.assertNotContains(self.client.get('/'),'Despesa confidencial')
        self.assertEqual(self.client.get('/contas/receivable/').status_code,200)

    def test_all_main_pages_render(self):
        self.client.force_login(self.admin)
        entry=Entry.objects.create(kind='receivable',title='Teste',amount=100,due=timezone.localdate())
        for url in ['/','/contas/payable/','/contas/receivable/','/contas/payable/nova/','/produtos/','/produtos/novo/','/contatos/','/contatos/novo/','/vendas/','/vendas/nova/','/usuarios/','/usuarios/novo/','/lembretes/','/historico/','/senha/',f'/conta/{entry.pk}/',f'/conta/{entry.pk}/editar/',f'/conta/{entry.pk}/baixa/']:
            self.assertEqual(self.client.get(url).status_code,200,url)

    def test_prevent_self_admin_removal(self):
        self.client.force_login(self.admin)
        result=self.client.post(f'/usuarios/{self.admin.pk}/editar/',{'name':'Admin','email':'admin@example.com','active':'on'})
        self.assertContains(result,'Você não pode remover')
        self.admin.refresh_from_db();self.assertTrue(self.admin.is_superuser)

    @override_settings(EVOLUTION_URL='https://example.com',EVOLUTION_KEY='test',EVOLUTION_INSTANCE='principal')
    @patch('finance.notifications.requests.post')
    def test_reminders_only_open_entries_and_single_owner(self,post):
        post.return_value=Mock(status_code=201)
        NotificationSettings.objects.create(pk=1,enabled=True,hour=0,phone='5565998040550')
        Entry.objects.create(kind='receivable',title='Aberta',amount=100,due=timezone.localdate())
        Entry.objects.create(kind='payable',title='Quitada',amount=100,paid=100,due=timezone.localdate())
        Entry.objects.create(kind='payable',title='Cancelada',amount=100,cancelled=True,due=timezone.localdate())
        send_daily_summary();send_daily_summary()
        post.assert_called_once()
        payload=post.call_args.kwargs['json']
        self.assertEqual(payload['number'],'5565998040550')
        self.assertIn('Aberta',payload['text']);self.assertNotIn('Quitada',payload['text']);self.assertNotIn('Cancelada',payload['text'])

    def test_cancel_future_preserves_paid_history(self):
        rule=Recurrence.objects.create(kind='payable',title='Mensal',amount=100,start=date(2026,1,1))
        generate_recurrences(date(2026,3,1))
        rows=list(Entry.objects.filter(recurrence=rule))
        settle(rows[2].pk,Decimal(10),timezone.localdate(),'',self.admin,uuid.uuid4())
        self.client.force_login(self.admin)
        self.client.post(f'/conta/{rows[0].pk}/cancelar/',{'scope':'future'})
        rows[2].refresh_from_db();rule.refresh_from_db()
        self.assertFalse(rows[2].cancelled);self.assertFalse(rule.active)

    def test_sale_cannot_cancel_paid_installments(self):
        sale=create_sale({'contact':self.contact,'product':self.product,'quantity':1,'unit_price':Decimal('100'),'installments':2,'first_due':timezone.localdate()},self.admin)
        entry=Entry.objects.filter(sale=sale).first();settle(entry.pk,Decimal(5),timezone.localdate(),'',self.admin,uuid.uuid4())
        self.client.force_login(self.admin);self.client.post(f'/vendas/{sale.pk}/cancelar/')
        sale.refresh_from_db();self.assertFalse(sale.cancelled)

    def test_login_throttled(self):
        for _ in range(10):self.client.post('/login/',{'email':'bad@example.com','password':'bad'})
        result=self.client.post('/login/',{'email':'bad@example.com','password':'bad'})
        self.assertContains(result,'Muitas tentativas')
