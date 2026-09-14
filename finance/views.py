import hashlib
import uuid
from datetime import date, timedelta
from decimal import Decimal
from functools import wraps
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import F, Sum, Q
from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_POST
from .models import Entry, Recurrence, Product, Contact, Sale, Audit, NotificationSettings, NotificationLog, LoginAttempt
from .forms import EntryForm, PaymentForm, ProductForm, ContactForm, SaleForm, UserForm, NotificationForm
from .services import audit, add_months, settle, create_sale, generate_recurrences

def allowed(user, area, action='view'):
    return user.has_perm(f'finance.{action}_{area}')

def require_area(area, action='view'):
    def decorate(fn):
        @login_required
        @wraps(fn)
        def wrapped(request,*args,**kwargs):
            target=kwargs.get('kind',area)
            if target not in ['payable','receivable','products','contacts','sales'] or not allowed(request.user,target,action): raise PermissionDenied
            return fn(request,*args,**kwargs)
        return wrapped
    return decorate

def admin_only(fn):
    @login_required
    @wraps(fn)
    def wrapped(request,*args,**kwargs):
        if not request.user.is_superuser: raise PermissionDenied
        return fn(request,*args,**kwargs)
    return wrapped

def login_view(request):
    if request.user.is_authenticated: return redirect('dashboard')
    error=None
    if request.method=='POST':
        email=request.POST.get('email','').strip().lower()
        ip=request.META.get('HTTP_X_REAL_IP',request.META.get('REMOTE_ADDR',''))
        keys=[hashlib.sha256(value.encode()).hexdigest() for value in ['ip:'+ip,'email:'+email]]
        now=timezone.now()
        attempts=[]
        for key in keys:
            attempt,_=LoginAttempt.objects.get_or_create(key=key)
            if now-attempt.since>timedelta(minutes=15):
                attempt.count=0;attempt.since=now;attempt.save()
            attempts.append(attempt)
        if any(a.count>=10 for a in attempts): error='Muitas tentativas. Aguarde 15 minutos e tente novamente.'
        else:
            user=authenticate(request,username=email,password=request.POST.get('password',''))
            if user:
                LoginAttempt.objects.filter(key=keys[1]).delete()
                login(request,user)
                return redirect('dashboard')
            LoginAttempt.objects.filter(key__in=keys).update(count=F('count')+1)
            error='E-mail ou senha incorretos.'
    return render(request,'login.html',{'error':error})

@require_POST
def logout_view(request):
    logout(request)
    return redirect('login')

@login_required
def dashboard(request):
    today=timezone.localdate()
    month=today.replace(day=1)
    end=add_months(month,1)
    kinds=[k for k in ['payable','receivable'] if allowed(request.user,k)]
    entries=Entry.objects.filter(kind__in=kinds,cancelled=False)
    opened=entries.filter(paid__lt=F('amount'))
    def total(qs): return qs.aggregate(value=Sum(F('amount')-F('paid')))['value'] or Decimal(0)
    payable=total(opened.filter(kind='payable',due__gte=month,due__lt=end)) if 'payable' in kinds else None
    receivable=total(opened.filter(kind='receivable',due__gte=month,due__lt=end)) if 'receivable' in kinds else None
    daily=[]
    for offset in range(7):
        day=today+timedelta(days=offset)
        incoming=total(opened.filter(kind='receivable',due=day));outgoing=total(opened.filter(kind='payable',due=day))
        daily.append({'date':day,'incoming':incoming,'outgoing':outgoing})
    maximum=max([max(d['incoming'],d['outgoing']) for d in daily]+[Decimal(1)])
    for d in daily:
        d['in_height']=max(2,int(d['incoming']/maximum*120));d['out_height']=max(2,int(d['outgoing']/maximum*120))
    return render(request,'dashboard.html',{'title':'Visão geral','today':today,'payable':payable,'receivable':receivable,'balance':receivable-payable if payable is not None and receivable is not None else None,'overdue':total(opened.filter(due__lt=today)),'upcoming':opened.select_related('contact')[:8],'daily':daily,'open_count':opened.count(),'overdue_count':opened.filter(due__lt=today).count(),'can_pay':allowed(request.user,'payable','add'),'can_receive':allowed(request.user,'receivable','add')})

@require_area('', 'view')
def entries(request,kind):
    qs=Entry.objects.filter(kind=kind).select_related('contact')
    query=request.GET.get('q','').strip()
    status=request.GET.get('status','open')
    if query: qs=qs.filter(Q(title__icontains=query)|Q(contact__name__icontains=query)|Q(category__icontains=query))
    if status=='paid': qs=qs.filter(cancelled=False,paid=F('amount'))
    elif status=='overdue': qs=qs.filter(cancelled=False,paid__lt=F('amount'),due__lt=timezone.localdate())
    elif status=='cancelled': qs=qs.filter(cancelled=True)
    elif status=='open': qs=qs.filter(cancelled=False,paid__lt=F('amount'))
    for key,lookup in [('from','due__gte'),('to','due__lte')]:
        try:
            if request.GET.get(key): qs=qs.filter(**{lookup:date.fromisoformat(request.GET[key])})
        except ValueError: messages.error(request,'Data de filtro inválida.')
    from django.core.paginator import Paginator
    page=Paginator(qs,30).get_page(request.GET.get('page'))
    params=request.GET.copy();params.pop('page',None)
    return render(request,'entries.html',{'title':'Contas a pagar' if kind=='payable' else 'Contas a receber','kind':kind,'page':page,'query':query,'status':status,'params':params.urlencode(),'total':qs.filter(cancelled=False).aggregate(v=Sum(F('amount')-F('paid')))['v'] or 0,'can_add':allowed(request.user,kind,'add'),'can_settle':allowed(request.user,kind,'settle')})

@require_area('', 'add')
def entry_new(request,kind):
    form=EntryForm(request.POST or None,initial={'due':timezone.localdate(),'repeat':'0'})
    if request.method=='POST' and form.is_valid():
        with transaction.atomic():
            entry=form.save(commit=False);entry.kind=kind
            repeat=int(form.cleaned_data.get('repeat') or 0)
            if repeat:
                rule=Recurrence.objects.create(kind=kind,title=entry.title,amount=entry.amount,contact=entry.contact,category=entry.category,start=entry.due,end=form.cleaned_data.get('end'),interval=repeat)
                generate_recurrences(max(add_months(timezone.localdate(),12),entry.due))
                entry=Entry.objects.get(recurrence=rule,sequence=0)
            else: entry.save()
            audit(request.user,f'Conta #{entry.pk} criada: {entry.title}.')
        messages.success(request,'Conta cadastrada com sucesso.')
        return redirect('entries',kind=kind)
    return render(request,'form.html',{'title':'Nova conta a pagar' if kind=='payable' else 'Nova conta a receber','form':form,'back':f'/contas/{kind}/','hint':'Recorrências geram os próximos 12 meses e continuam automaticamente. Datas no fim do mês são ajustadas ao último dia válido.'})

@login_required
def entry_detail(request,pk):
    entry=get_object_or_404(Entry.objects.select_related('contact','recurrence'),pk=pk)
    if not allowed(request.user,entry.kind): raise PermissionDenied
    return render(request,'entry_detail.html',{'title':entry.title,'entry':entry,'payments':entry.payments.select_related('user'),'can_settle':allowed(request.user,entry.kind,'settle'),'can_change':allowed(request.user,entry.kind,'change'),'can_delete':allowed(request.user,entry.kind,'delete')})

@login_required
def entry_edit(request,pk):
    entry=get_object_or_404(Entry,pk=pk)
    if not allowed(request.user,entry.kind,'change'): raise PermissionDenied
    if entry.cancelled or entry.paid>0 or entry.sale_id:
        messages.error(request,'Contas com baixa, canceladas ou geradas por vendas não podem ser editadas.');return redirect('entry_detail',pk=pk)
    form=EntryForm(request.POST or None,instance=entry)
    if request.method=='POST' and form.is_valid():
        with transaction.atomic():
            locked=Entry.objects.select_for_update().get(pk=pk)
            if locked.paid>0 or locked.cancelled:
                messages.error(request,'A conta foi alterada. Atualize a página.');return redirect('entry_detail',pk=pk)
            obj=form.save()
            if request.POST.get('scope')=='future' and obj.recurrence_id:
                rule=Recurrence.objects.select_for_update().get(pk=obj.recurrence_id)
                rule.title=obj.title;rule.amount=obj.amount;rule.contact=obj.contact;rule.category=obj.category;rule.save()
                Entry.objects.filter(recurrence=rule,sequence__gt=obj.sequence,paid=0,cancelled=False).update(title=obj.title,amount=obj.amount,contact=obj.contact,category=obj.category)
            audit(request.user,f'Conta #{pk} editada; escopo: {request.POST.get("scope","one")}.')
        messages.success(request,'Conta atualizada.');return redirect('entry_detail',pk=pk)
    return render(request,'form.html',{'title':'Editar conta','form':form,'back':f'/conta/{pk}/','scope':bool(entry.recurrence_id),'hint':'O vencimento é alterado somente nesta ocorrência. No escopo futuro, descrição, valor, contato e categoria são aplicados às próximas contas sem baixa.'})

@login_required
def entry_settle(request,pk):
    entry=get_object_or_404(Entry,pk=pk)
    if not allowed(request.user,entry.kind,'settle'): raise PermissionDenied
    form=PaymentForm(request.POST or None,initial={'amount':entry.balance,'date':timezone.localdate(),'token':uuid.uuid4()})
    if request.method=='POST' and form.is_valid():
        try:
            settle(pk,form.cleaned_data['amount'],form.cleaned_data['date'],form.cleaned_data['notes'],request.user,form.cleaned_data['token'])
            messages.success(request,'Baixa registrada.');return redirect('entry_detail',pk=pk)
        except ValueError as exc: form.add_error(None,str(exc))
    return render(request,'form.html',{'title':'Registrar baixa','form':form,'back':f'/conta/{pk}/','hint':entry.title})

@login_required
@require_POST
def entry_cancel(request,pk):
    with transaction.atomic():
        entry=get_object_or_404(Entry.objects.select_for_update(),pk=pk)
        if not allowed(request.user,entry.kind,'delete'): raise PermissionDenied
        if entry.paid or entry.sale_id:
            messages.error(request,'Contas com baixa não podem ser canceladas. Parcelas devem ser canceladas pela venda.')
        else:
            entry.cancelled=True;entry.save(update_fields=['cancelled'])
            if request.POST.get('scope')=='future' and entry.recurrence_id:
                rule=Recurrence.objects.select_for_update().get(pk=entry.recurrence_id);rule.active=False;rule.save()
                Entry.objects.filter(recurrence=rule,sequence__gt=entry.sequence,paid=0).update(cancelled=True)
            audit(request.user,f'Conta #{pk} cancelada; escopo: {request.POST.get("scope","one")}.');messages.success(request,'Cancelamento registrado.')
    return redirect('entry_detail',pk=pk)

CATALOGS={'products':(Product,ProductForm,'Produtos','/produtos/'),'contacts':(Contact,ContactForm,'Clientes e fornecedores','/contatos/')}

@login_required
def catalog(request,area):
    if not allowed(request.user,area): raise PermissionDenied
    model,_,title,path=CATALOGS[area]
    qs=model.objects.filter(active=True)
    query=request.GET.get('q','').strip()
    if query: qs=qs.filter(name__icontains=query)
    return render(request,'catalog.html',{'title':title,'items':qs[:200],'area':area,'path':path,'query':query,'can_add':allowed(request.user,area,'add'),'can_change':allowed(request.user,area,'change'),'can_delete':allowed(request.user,area,'delete')})

@login_required
def catalog_edit(request,area,pk=None):
    if not allowed(request.user,area,'change' if pk else 'add'): raise PermissionDenied
    model,form_class,title,path=CATALOGS[area]
    obj=get_object_or_404(model,pk=pk,active=True) if pk else None
    form=form_class(request.POST or None,instance=obj)
    if request.method=='POST' and form.is_valid():
        obj=form.save();audit(request.user,f'{title}: cadastro #{obj.pk} salvo.');messages.success(request,'Cadastro salvo.');return redirect(path)
    return render(request,'form.html',{'title':('Editar' if pk else 'Novo cadastro')+' · '+title,'form':form,'back':path})

@login_required
@require_POST
def catalog_delete(request,area,pk):
    if not allowed(request.user,area,'delete'): raise PermissionDenied
    model,_,title,path=CATALOGS[area]
    obj=get_object_or_404(model,pk=pk);obj.active=False;obj.save(update_fields=['active'])
    audit(request.user,f'{title}: cadastro #{pk} arquivado.');messages.success(request,'Cadastro arquivado. O histórico foi preservado.');return redirect(path)

@require_area('sales')
def sales(request):
    return render(request,'sales.html',{'title':'Vendas parceladas','sales':Sale.objects.select_related('contact')[:200],'can_add':allowed(request.user,'sales','add') and allowed(request.user,'receivable','add'),'can_delete':allowed(request.user,'sales','delete') and allowed(request.user,'receivable','delete')})

@require_area('sales','add')
def sale_new(request):
    if not allowed(request.user,'receivable','add'): raise PermissionDenied
    form=SaleForm(request.POST or None,initial={'first_due':timezone.localdate()})
    if request.method=='POST' and form.is_valid():
        try:
            create_sale(form.cleaned_data,request.user);messages.success(request,'Venda cadastrada. As parcelas foram geradas em contas a receber.');return redirect('sales')
        except ValueError as exc: form.add_error(None,str(exc))
    return render(request,'form.html',{'title':'Nova venda parcelada','form':form,'back':'/vendas/','hint':'Cadastre o cliente e o produto antes da venda. O valor total é dividido em parcelas mensais, sem perder centavos.','product_prices':{str(p.pk):str(p.price) for p in Product.objects.filter(active=True)}})

@require_area('sales','delete')
@require_POST
def sale_cancel(request,pk):
    if not allowed(request.user,'receivable','delete'): raise PermissionDenied
    with transaction.atomic():
        sale=get_object_or_404(Sale.objects.select_for_update(),pk=pk)
        entries=list(Entry.objects.select_for_update().filter(sale=sale))
        if any(e.paid>0 for e in entries): messages.error(request,'Esta venda já tem recebimentos e não pode ser cancelada.')
        else:
            Entry.objects.filter(sale=sale).update(cancelled=True);sale.cancelled=True;sale.save();audit(request.user,f'Venda #{pk} cancelada.');messages.success(request,'Venda e parcelas canceladas.')
    return redirect('sales')

AREAS=[('payable','Contas a pagar'),('receivable','Contas a receber'),('products','Produtos'),('contacts','Clientes e fornecedores'),('sales','Vendas')]
ACTIONS=[('view','Visualizar'),('add','Cadastrar'),('change','Editar'),('delete','Cancelar / arquivar'),('settle','Dar baixa')]

@admin_only
def users(request):
    return render(request,'users.html',{'title':'Usuários e permissões','users':get_user_model().objects.order_by('first_name')})

@admin_only
def user_edit(request,pk=None):
    user=get_object_or_404(get_user_model(),pk=pk) if pk else None
    initial={'name':user.first_name,'email':user.email,'admin':user.is_superuser,'active':user.is_active} if user else {}
    form=UserForm(request.POST or None,instance=user,initial=initial)
    selected=request.POST.getlist('permissions') if request.method=='POST' else list(user.user_permissions.values_list('codename',flat=True)) if user else []
    if request.method=='POST' and form.is_valid():
        data=form.cleaned_data
        if user and user.pk==request.user.pk and (not data['admin'] or not data['active']): form.add_error(None,'Você não pode remover seu próprio acesso de administrador.')
        else:
            with transaction.atomic():
                user=user or get_user_model()()
                user.username=data['email'];user.email=data['email'];user.first_name=data['name'];user.is_superuser=data['admin'];user.is_active=data['active']
                if data['password']: user.set_password(data['password'])
                user.save()
                valid={f'{action}_{area}' for area,_ in AREAS for action,_ in ACTIONS}
                perms=set(selected)&valid
                for perm in list(perms): perms.add('view_'+perm.split('_',1)[1])
                user.user_permissions.set(Permission.objects.filter(content_type__app_label='finance',codename__in=perms))
                audit(request.user,f'Usuário #{user.pk} e permissões atualizados.')
            messages.success(request,'Usuário salvo.');return redirect('users')
    rows=[{'label':label,'cells':[{'name':f'{action}_{area}','checked':f'{action}_{area}' in selected,'disabled':action=='settle' and area not in ['payable','receivable']} for action,_ in ACTIONS]} for area,label in AREAS]
    return render(request,'form.html',{'title':'Editar usuário' if pk else 'Novo usuário','form':form,'back':'/usuarios/','permission_rows':rows,'actions':ACTIONS})

@admin_only
def notifications(request):
    obj,_=NotificationSettings.objects.get_or_create(pk=1)
    form=NotificationForm(request.POST or None,instance=obj)
    if request.method=='POST' and form.is_valid():
        form.save();audit(request.user,'Configuração de lembretes atualizada.');messages.success(request,'Preferências salvas.');return redirect('notifications')
    from django.conf import settings
    return render(request,'notifications.html',{'title':'Lembretes no WhatsApp','form':form,'connected':bool(settings.EVOLUTION_KEY and settings.EVOLUTION_INSTANCE),'logs':NotificationLog.objects.order_by('-date')[:14]})

@admin_only
def history(request):
    return render(request,'history.html',{'title':'Histórico de atividades','logs':Audit.objects.select_related('user')[:150]})

def health(request): return HttpResponse('ok',content_type='text/plain')
