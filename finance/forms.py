from decimal import Decimal
from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from .models import Contact, Product, Entry, NotificationSettings

class DateInput(forms.DateInput):
    input_type = 'date'
    def __init__(self, **kwargs): super().__init__(format='%Y-%m-%d', **kwargs)

class EntryForm(forms.ModelForm):
    repeat = forms.ChoiceField(label='Repetição', choices=[('0','Não se repete'),('1','Mensal'),('3','Trimestral'),('12','Anual')], required=False)
    end = forms.DateField(label='Repetir até (opcional)', required=False, widget=DateInput())
    class Meta:
        model = Entry
        fields = ['title','amount','due','contact','category','notes']
        widgets = {'due':DateInput(),'notes':forms.Textarea(attrs={'rows':3})}
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields['contact'].queryset = Contact.objects.filter(active=True)
        if self.instance.pk:
            del self.fields['repeat']; del self.fields['end']
    def clean(self):
        data=super().clean()
        if data.get('end') and data.get('due') and data['end'] < data['due']: self.add_error('end','A data final deve ser igual ou posterior ao primeiro vencimento.')
        return data

class PaymentForm(forms.Form):
    amount = forms.DecimalField(label='Valor pago / recebido', max_digits=12, decimal_places=2, min_value=Decimal('.01'))
    date = forms.DateField(label='Data da baixa',widget=DateInput())
    notes = forms.CharField(label='Observação', max_length=240,required=False)
    token = forms.UUIDField(widget=forms.HiddenInput())

class ProductForm(forms.ModelForm):
    class Meta:
        model=Product
        fields=['name','sku','price','notes']
        widgets={'notes':forms.Textarea(attrs={'rows':3})}

class ContactForm(forms.ModelForm):
    class Meta:
        model=Contact
        fields=['name','kind','phone','email','notes']
        widgets={'notes':forms.Textarea(attrs={'rows':3})}

class SaleForm(forms.Form):
    contact=forms.ModelChoiceField(label='Cliente',queryset=Contact.objects.none())
    product=forms.ModelChoiceField(label='Produto',queryset=Product.objects.none())
    quantity=forms.IntegerField(label='Quantidade',min_value=1,max_value=100000,initial=1)
    unit_price=forms.DecimalField(label='Preço unitário',max_digits=12,decimal_places=2,min_value=Decimal('.01'))
    installments=forms.IntegerField(label='Número de parcelas mensais',min_value=1,max_value=120,initial=1)
    first_due=forms.DateField(label='Primeiro vencimento',widget=DateInput())
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields['contact'].queryset=Contact.objects.filter(active=True,kind__in=['customer','both'])
        self.fields['product'].queryset=Product.objects.filter(active=True)

class UserForm(forms.Form):
    name=forms.CharField(label='Nome',max_length=150)
    email=forms.EmailField(label='E-mail de acesso')
    password=forms.CharField(label='Senha (mínimo de 12 caracteres)',widget=forms.PasswordInput,required=False)
    admin=forms.BooleanField(label='Administrador — acesso completo',required=False)
    active=forms.BooleanField(label='Usuário ativo',required=False,initial=True)
    def __init__(self,*args,instance=None,**kwargs):
        self.instance=instance
        super().__init__(*args,**kwargs)
        if not instance: self.fields['password'].required=True
    def clean_email(self):
        email=self.cleaned_data['email'].lower()
        users=get_user_model().objects.filter(username__iexact=email)
        if self.instance: users=users.exclude(pk=self.instance.pk)
        if users.exists(): raise forms.ValidationError('Este e-mail já está cadastrado.')
        return email
    def clean(self):
        data=super().clean()
        if data.get('password'):
            candidate=get_user_model()(username=data.get('email',''),email=data.get('email',''),first_name=data.get('name',''))
            try: validate_password(data['password'],candidate)
            except forms.ValidationError as exc: self.add_error('password',exc)
        return data

class NotificationForm(forms.ModelForm):
    class Meta:
        model=NotificationSettings
        fields=['phone','enabled','days_before','hour','overdue']
