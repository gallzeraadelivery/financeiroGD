def navigation(request):
    user = request.user
    areas = [('payable', 'Contas a pagar', '/contas/payable/', '↗'), ('receivable', 'Contas a receber', '/contas/receivable/', '↙'), ('sales', 'Vendas parceladas', '/vendas/', '▤'), ('products', 'Produtos', '/produtos/', '◇'), ('contacts', 'Clientes e fornecedores', '/contatos/', '♧')]
    return {'navigation': [{'label': label, 'url': url, 'icon': icon} for area, label, url, icon in areas if user.is_authenticated and user.has_perm('finance.view_' + area)]}
