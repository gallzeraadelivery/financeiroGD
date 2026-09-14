from decimal import Decimal
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator, RegexValidator
from django.db import models
from django.utils import timezone

class Access(models.Model):
    class Meta:
        managed = False
        default_permissions = ()
        permissions = [(f'{action}_{area}', f'{action} {area}') for area in ['payable', 'receivable', 'products', 'contacts', 'sales'] for action in ['view', 'add', 'change', 'delete', 'settle']]

class Contact(models.Model):
    name = models.CharField('Nome', max_length=160)
    kind = models.CharField('Tipo', max_length=12, choices=[('customer', 'Cliente'), ('supplier', 'Fornecedor'), ('both', 'Cliente e fornecedor')])
    phone = models.CharField('WhatsApp', max_length=20, blank=True)
    email = models.EmailField('E-mail', blank=True)
    notes = models.TextField('Observações', blank=True)
    active = models.BooleanField(default=True)
    def __str__(self): return self.name
    class Meta: ordering = ['name']

class Product(models.Model):
    name = models.CharField('Nome do produto', max_length=160)
    sku = models.CharField('Código', max_length=60, blank=True)
    price = models.DecimalField('Preço de venda', max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    notes = models.TextField('Descrição', blank=True)
    active = models.BooleanField(default=True)
    def __str__(self): return self.name
    class Meta: ordering = ['name']

class Recurrence(models.Model):
    kind = models.CharField(max_length=10)
    title = models.CharField(max_length=180)
    contact = models.ForeignKey(Contact, null=True, blank=True, on_delete=models.PROTECT)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    category = models.CharField(max_length=80, blank=True)
    start = models.DateField()
    end = models.DateField(null=True, blank=True)
    interval = models.PositiveSmallIntegerField(default=1)
    next_index = models.PositiveIntegerField(default=0)
    active = models.BooleanField(default=True)

class Sale(models.Model):
    contact = models.ForeignKey(Contact, on_delete=models.PROTECT)
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    product_name = models.CharField(max_length=160)
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1), MaxValueValidator(100000)])
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    total = models.DecimalField(max_digits=12, decimal_places=2)
    installments = models.PositiveSmallIntegerField()
    first_due = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)
    cancelled = models.BooleanField(default=False)
    class Meta: ordering = ['-created_at']

class Entry(models.Model):
    KINDS = [('payable', 'Conta a pagar'), ('receivable', 'Conta a receber')]
    kind = models.CharField(max_length=10, choices=KINDS)
    title = models.CharField('Descrição', max_length=180)
    contact = models.ForeignKey(Contact, verbose_name='Cliente / fornecedor', null=True, blank=True, on_delete=models.PROTECT)
    amount = models.DecimalField('Valor', max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    paid = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    due = models.DateField('Vencimento')
    category = models.CharField('Categoria', max_length=80, blank=True)
    notes = models.TextField('Observações', blank=True)
    recurrence = models.ForeignKey(Recurrence, null=True, on_delete=models.PROTECT)
    sale = models.ForeignKey(Sale, null=True, on_delete=models.PROTECT)
    sequence = models.PositiveIntegerField(default=0)
    cancelled = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ['due', 'id']
        constraints = [models.CheckConstraint(condition=models.Q(amount__gt=0), name='entry_positive_amount'), models.CheckConstraint(condition=models.Q(paid__gte=0) & models.Q(paid__lte=models.F('amount')), name='entry_paid_bounds'), models.UniqueConstraint(fields=['recurrence','sequence'], name='unique_recurrence_entry')]
    @property
    def balance(self): return self.amount - self.paid
    @property
    def status(self):
        if self.cancelled: return 'Cancelado'
        if self.balance == 0: return 'Quitado'
        if self.due < timezone.localdate(): return 'Em atraso'
        if self.paid > 0: return 'Parcial'
        if self.due == timezone.localdate(): return 'Vence hoje'
        return 'Em aberto'
    @property
    def status_class(self):
        return {'Cancelado':'muted','Quitado':'green','Em atraso':'red','Parcial':'amber','Vence hoje':'amber','Em aberto':'blue'}[self.status]

class Payment(models.Model):
    entry = models.ForeignKey(Entry, related_name='payments', on_delete=models.PROTECT)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    date = models.DateField()
    notes = models.CharField(max_length=240, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    token = models.UUIDField(unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta: ordering = ['-date', '-id']

class Audit(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=240)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta: ordering = ['-created_at']

class NotificationSettings(models.Model):
    phone = models.CharField('Seu WhatsApp (país + DDD + número)', max_length=15, validators=[RegexValidator(r'^\d{12,15}$', 'Use somente números, incluindo país e DDD.')], default='5565998040550')
    enabled = models.BooleanField('Ativar lembretes automáticos', default=False)
    days_before = models.PositiveSmallIntegerField('Avisar quantos dias antes?', default=3, validators=[MaxValueValidator(30)])
    hour = models.PositiveSmallIntegerField('Horário do resumo (hora de Cuiabá)', default=8, validators=[MaxValueValidator(23)])
    overdue = models.BooleanField('Incluir contas em atraso', default=True)

class NotificationLog(models.Model):
    date = models.DateField(unique=True)
    status = models.CharField(max_length=16, default='pending')
    detail = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

class LoginAttempt(models.Model):
    key = models.CharField(max_length=64, unique=True)
    count = models.PositiveIntegerField(default=0)
    since = models.DateTimeField(default=timezone.now)
