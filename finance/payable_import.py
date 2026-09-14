import hashlib
import json
import uuid
from collections import Counter
from datetime import datetime
from decimal import Decimal, InvalidOperation
from django.db import transaction
from .models import Audit, Contact, Entry, ImportedPayable, Payment

FIELDS = ['Descrição do recebimento', 'Situação', 'Plano de contas', 'Entidade',
          'Entidade Nome', 'Valor', 'Desconto', 'Juros', 'Taxa do banco',
          'Taxa da operadora', 'Valor total', 'Data do vencimento',
          'Data de competência', 'Data de confirmação', 'Forma de pagamento',
          'Conta bancária', 'Centro de custo', 'Observações', 'Cadastrado por',
          'Cadastrado em', 'Modificado em']

def money(value):
    text = str(value).strip()
    if ',' in text:
        text = text.replace('.', '').replace(',', '.')
    try:
        result = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError('Valor monetário inválido.') from exc
    if not result.is_finite() or result != result.quantize(Decimal('.01')):
        raise ValueError('Valor monetário deve ter no máximo duas casas decimais.')
    return result

def normalize(payload):
    if payload.get('format') != 'payables-export-v1' or not payload.get('rows'):
        raise ValueError('Formato de importação inválido ou sem registros.')
    result = []
    for item in payload['rows']:
        raw = item['values']
        if set(raw) != set(FIELDS):
            raise ValueError(f'Colunas inesperadas na linha {item["row"]}.')
        title = str(raw[FIELDS[0]] or '').strip()
        category = str(raw['Plano de contas'] or '').strip()
        contact = str(raw['Entidade Nome'] or '').strip()
        if not title or len(title)>180 or len(category)>80 or len(contact)>160:
            raise ValueError(f'Descrição ou cadastro inválido na linha {item["row"]}.')
        amount = money(raw['Valor total'])
        expected = money(raw['Valor'])-money(raw['Desconto'])+sum(money(raw[f]) for f in ['Juros','Taxa do banco','Taxa da operadora'])
        if amount <= 0 or amount > Decimal('9999999999.99') or amount != expected:
            raise ValueError(f'Total inconsistente na linha {item["row"]}.')
        due = datetime.strptime(raw['Data do vencimento'], '%d/%m/%Y').date()
        confirmed = datetime.strptime(raw['Data de confirmação'], '%d/%m/%Y').date() if raw['Data de confirmação'] else None
        status = raw['Situação']
        if status not in ['Confirmado','Atrasado'] or (status=='Confirmado') != bool(confirmed):
            raise ValueError(f'Situação e confirmação incompatíveis na linha {item["row"]}.')
        created = datetime.strptime(raw['Cadastrado em'], '%d/%m/%Y %H:%M:%S').isoformat()
        identity = json.dumps(['payables-export-v1',title,due.isoformat(),created],ensure_ascii=False)
        key = hashlib.sha256(identity.encode()).hexdigest()
        result.append({'key':key,'title':title,'category':category,'contact':contact,'amount':amount,
                       'due':due,'confirmed':confirmed,'raw':raw,'row':item['row']})
    if len({r['key'] for r in result}) != len(result):
        raise ValueError('Há registros repetidos com a mesma identificação de origem.')
    return result

@transaction.atomic
def import_payables(payload, user, apply=False):
    rows = normalize(payload)
    # Serialize imports across workers without exposing a new public upload endpoint.
    type(user).objects.select_for_update().get(pk=user.pk)
    groups = Counter((r['title'].casefold(),r['due']) for r in rows)
    stats = {'rows':len(rows),'created':0,'skipped':0,'paid_count':0,'open_count':0,
             'total':Decimal(0),'paid':Decimal(0),'open':Decimal(0),'review_rows':[]}
    for row in rows:
        stats['total'] += row['amount']
        bucket = 'paid' if row['confirmed'] else 'open'
        stats[bucket] += row['amount']; stats[bucket+'_count'] += 1
        existing = ImportedPayable.objects.filter(source_key=row['key']).first()
        if existing:
            if existing.original != row['raw']:
                raise ValueError(f'A linha {row["row"]} já foi importada com dados diferentes; revisão necessária.')
            stats['skipped'] += 1
            continue
        if Entry.objects.filter(kind='payable',title=row['title'],due=row['due'],amount=row['amount']).exists():
            raise ValueError(f'Já existe uma conta equivalente à linha {row["row"]}; revise antes de importar.')
        review = groups[(row['title'].casefold(),row['due'])]>1
        if review: stats['review_rows'].append(row['row'])
        stats['created'] += 1
        if not apply: continue
        contact = None
        if row['contact']:
            contacts = list(Contact.objects.filter(name__iexact=row['contact']))
            if len(contacts)>1: raise ValueError(f'Contato ambíguo na linha {row["row"]}.')
            if contacts:
                contact=contacts[0]
                if contact.kind=='customer':
                    contact.kind='both';contact.save(update_fields=['kind'])
            else:
                contact=Contact.objects.create(name=row['contact'],kind='supplier')
        notes=[f'Importado de {payload["file"]} · {payload["sheet"]}, linha {row["row"]}.']
        if review:
            notes.append('CONFERIR POSSÍVEL DUPLICIDADE: outra conta na planilha tem a mesma descrição e vencimento, com identificação própria. Ambas foram preservadas.')
        notes.extend(f'{label}: {row["raw"][label]}' for label in FIELDS if row['raw'][label] is not None and row['raw'][label]!='')
        entry=Entry.objects.create(kind='payable',title=row['title'],contact=contact,amount=row['amount'],
                                   paid=row['amount'] if row['confirmed'] else 0,due=row['due'],
                                   category=row['category'],notes='\n'.join(notes))
        if row['confirmed']:
            Payment.objects.create(entry=entry,amount=row['amount'],date=row['confirmed'],user=user,
                                   notes=f'Baixa histórica importada. Responsável na origem: {row["raw"]["Cadastrado por"]}',
                                   token=uuid.uuid5(uuid.NAMESPACE_URL,'financeiro-import:'+row['key']))
        ImportedPayable.objects.create(source_key=row['key'],entry=entry,source_file=payload['file'],
                                      source_row=row['row'],original=row['raw'])
    if apply and stats['created']:
        Audit.objects.create(user=user,action=f'Importação de contas a pagar: {stats["created"]} criadas, {stats["skipped"]} já importadas. Origem: {payload["file"]}.')
    return stats
