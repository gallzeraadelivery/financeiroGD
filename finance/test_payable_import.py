from copy import deepcopy
from decimal import Decimal
from django.test import TestCase
from django.contrib.auth import get_user_model
from .models import Entry, Payment, ImportedPayable, Contact
from .payable_import import FIELDS, import_payables

def payload():
    raw = dict.fromkeys(FIELDS)
    raw.update({'Descrição do recebimento':'Conta exemplo','Situação':'Confirmado',
                'Plano de contas':'Serviços','Entidade':'Fornecedor','Entidade Nome':'Fornecedor exemplo',
                'Valor':'119.9','Desconto':'20','Juros':'0','Taxa do banco':'0','Taxa da operadora':'0',
                'Valor total':'99,90','Data do vencimento':'05/09/2025','Data de confirmação':'06/09/2025',
                'Cadastrado em':'01/09/2025 10:00:00','Cadastrado por':'Operador antigo'})
    return {'format':'payables-export-v1','file':'fixture.xlsx','sheet':'Worksheet','rows':[{'row':2,'values':raw}]}

class PayableImportTests(TestCase):
    def setUp(self):
        self.user=get_user_model().objects.create_superuser('admin@test.example',password='test')

    def test_dry_run_does_not_write(self):
        report=import_payables(payload(),self.user)
        self.assertEqual(report['paid'],Decimal('99.90'))
        self.assertEqual(Entry.objects.count(),0)
        self.assertEqual(Contact.objects.count(),0)

    def test_preserves_discount_payment_date_and_is_idempotent(self):
        data=payload()
        import_payables(data,self.user,apply=True)
        report=import_payables(data,self.user,apply=True)
        self.assertEqual(report['skipped'],1)
        entry=Entry.objects.get()
        self.assertEqual(entry.amount,Decimal('99.90'))
        self.assertEqual(entry.paid,entry.amount)
        self.assertEqual(Payment.objects.get().date.isoformat(),'2025-09-06')
        self.assertIn('Desconto: 20',entry.notes)
        self.assertIsNone(entry.recurrence_id)
        self.assertEqual(ImportedPayable.objects.get().original,data['rows'][0]['values'])

    def test_changed_source_requires_review(self):
        data=payload();import_payables(data,self.user,apply=True)
        data['rows'][0]['values']['Observações']='Changed after import'
        with self.assertRaises(ValueError):import_payables(data,self.user,apply=True)
        self.assertEqual(Entry.objects.count(),1)

    def test_ambiguous_rows_preserved_and_flagged(self):
        data=payload()
        first=data['rows'][0]['values'];first['Situação']='Atrasado';first['Data de confirmação']=None
        second=deepcopy(first);second['Cadastrado em']='01/09/2025 11:00:00'
        second['Valor']='100';second['Desconto']='0';second['Valor total']='100,00'
        data['rows'].append({'row':3,'values':second})
        report=import_payables(data,self.user,apply=True)
        self.assertEqual(report['review_rows'],[2,3])
        self.assertEqual(Entry.objects.count(),2)
        self.assertEqual(Payment.objects.count(),0)
        self.assertTrue(all('CONFERIR POSSÍVEL DUPLICIDADE' in e.notes for e in Entry.objects.all()))

    def test_late_conflict_rolls_back_entire_import(self):
        data=payload();second=deepcopy(data['rows'][0]['values'])
        second['Descrição do recebimento']='Existing'
        data['rows'].append({'row':3,'values':second})
        Entry.objects.create(kind='payable',title='Existing',due='2025-09-05',amount='99.90')
        with self.assertRaises(ValueError):import_payables(data,self.user,apply=True)
        self.assertEqual(Entry.objects.count(),1)
        self.assertEqual(Payment.objects.count(),0)
        self.assertEqual(Contact.objects.count(),0)

    def test_invalid_total_rejected(self):
        data=payload();data['rows'][0]['values']['Valor total']='100,00'
        with self.assertRaises(ValueError):import_payables(data,self.user,apply=True)
        self.assertEqual(Entry.objects.count(),0)
