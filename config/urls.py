from django.urls import path
from django.contrib.auth import views as auth_views
from finance import views

urlpatterns=[
 path('',views.dashboard,name='dashboard'),path('login/',views.login_view,name='login'),path('logout/',views.logout_view,name='logout'),
 path('senha/',auth_views.PasswordChangeView.as_view(template_name='form.html',success_url='/'),name='password_change'),
 path('contas/<str:kind>/',views.entries,name='entries'),path('contas/<str:kind>/nova/',views.entry_new,name='entry_new'),
 path('conta/<int:pk>/',views.entry_detail,name='entry_detail'),path('conta/<int:pk>/editar/',views.entry_edit,name='entry_edit'),path('conta/<int:pk>/baixa/',views.entry_settle,name='entry_settle'),path('conta/<int:pk>/cancelar/',views.entry_cancel,name='entry_cancel'),
 path('produtos/',views.catalog,{'area':'products'},name='products'),path('produtos/novo/',views.catalog_edit,{'area':'products'}),path('produtos/<int:pk>/editar/',views.catalog_edit,{'area':'products'}),path('produtos/<int:pk>/arquivar/',views.catalog_delete,{'area':'products'}),
 path('contatos/',views.catalog,{'area':'contacts'},name='contacts'),path('contatos/novo/',views.catalog_edit,{'area':'contacts'}),path('contatos/<int:pk>/editar/',views.catalog_edit,{'area':'contacts'}),path('contatos/<int:pk>/arquivar/',views.catalog_delete,{'area':'contacts'}),
 path('vendas/',views.sales,name='sales'),path('vendas/nova/',views.sale_new,name='sale_new'),path('vendas/<int:pk>/cancelar/',views.sale_cancel,name='sale_cancel'),
 path('usuarios/',views.users,name='users'),path('usuarios/novo/',views.user_edit,name='user_new'),path('usuarios/<int:pk>/editar/',views.user_edit,name='user_edit'),
 path('lembretes/',views.notifications,name='notifications'),path('historico/',views.history,name='history'),path('health/',views.health)
]
