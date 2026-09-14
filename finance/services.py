import calendar
from datetime import date
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from .models import Audit, Entry, Payment, Recurrence, Sale

def add_months(start, months):
    index = start.year * 12 + start.month - 1 + months
    year, month = divmod(index, 12)
    return date(year, month + 1, min(start.day, calendar.monthrange(year, month + 1)[1]))

def audit(user, action):
    Audit.objects.create(user=user if user and user.is_authenticated else None, action=action)

@transaction.atomic
def generate_recurrences(horizon=None):
    horizon = horizon or add_months(timezone.localdate(), 12)
    for rule in Recurrence.objects.select_for_update().filter(active=True):
        while True:
            due = add_months(rule.start, rule.next_index * rule.interval)
            if due > horizon or (rule.end and due > rule.end): break
            Entry.objects.get_or_create(recurrence=rule, sequence=rule.next_index, defaults={'kind':rule.kind,'title':rule.title,'contact':rule.contact,'amount':rule.amount,'due':due,'category':rule.category})
            rule.next_index += 1
        rule.save(update_fields=['next_index'])

@transaction.atomic
def settle(entry_id, amount, paid_date, notes, user, token):
    entry = Entry.objects.select_for_update().get(pk=entry_id)
    if Payment.objects.filter(token=token).exists(): return False
    if entry.cancelled or amount <= 0 or amount > entry.balance:
        raise ValueError('O valor deve ser maior que zero e não pode ultrapassar o saldo em aberto.')
    if paid_date > timezone.localdate(): raise ValueError('A data da baixa não pode estar no futuro.')
    Payment.objects.create(entry=entry,amount=amount,date=paid_date,notes=notes,user=user,token=token)
    entry.paid += amount
    entry.save(update_fields=['paid'])
    audit(user, f'Baixa na conta #{entry.pk}: {amount:.2f} em {paid_date}.')
    return True

@transaction.atomic
def create_sale(data, user):
    product = data['product']
    total = (data['unit_price'] * data['quantity']).quantize(Decimal('.01'))
    count = data['installments']
    if total > Decimal('9999999999.99'): raise ValueError('O total excede o limite permitido.')
    cents = int(total * 100)
    if cents < count: raise ValueError('Cada parcela deve ter pelo menos R$ 0,01.')
    sale = Sale.objects.create(product=product,product_name=product.name,contact=data['contact'],quantity=data['quantity'],unit_price=data['unit_price'],total=total,installments=count,first_due=data['first_due'])
    base, remainder = divmod(cents, count)
    for index in range(count):
        Entry.objects.create(kind='receivable',title=f'{product.name} · {index+1}/{count}',contact=sale.contact,amount=Decimal(base + (index < remainder))/100,due=add_months(sale.first_due,index),sale=sale,sequence=index,category='Vendas')
    audit(user, f'Venda #{sale.pk} criada: {total:.2f}, {count} parcelas.')
    return sale
