# Financeiro GD

Aplicação de contas a pagar e receber, publicada em https://financeiro.gdapps.online.

## Funcionalidades

- Login com sessões, proteção CSRF, senhas protegidas por hash e limite de tentativas.
- Contas avulsas e recorrentes mensais, trimestrais e anuais.
- Geração contínua dos próximos 12 meses; vencimentos ancorados no dia original, com ajuste ao último dia válido.
- Baixas parciais, validação do saldo e proteção contra reenvio da mesma baixa.
- Produtos, clientes e fornecedores; arquivamento preservando histórico.
- Vendas com até 120 parcelas mensais. O resto em centavos é distribuído nas primeiras parcelas.
- Permissões por área e ação, verificadas no servidor. Criar vendas exige também cadastrar contas a receber; cancelar exige as duas permissões de cancelamento.
- Resumo diário pelo WhatsApp, destinado somente ao número configurado pelo administrador. Clientes nunca são destinatários nesta versão.
- Registro de alterações e de envios. Uma tentativa por dia evita duplicação em respostas ambíguas da API.

## Desenvolvimento

Python 3.12+ e PostgreSQL 16 em produção; SQLite para desenvolvimento e testes rápidos.

```sh
python -m venv .venv
# Ative o ambiente conforme seu sistema operacional.
pip install -r requirements.txt
export DEBUG=1
python manage.py migrate
python manage.py runserver
python manage.py test finance
```

No PowerShell, use `$env:DEBUG='1'` no lugar de `export`.

## Produção

O código fica em `/opt/financeiro-gd`. Os segredos ficam apenas em `.env`, com permissão 600. Nunca versionar chaves, senhas ou cópias de banco. A chave da Evolution API é restrita à instância `principal`.

```sh
docker compose build
docker compose run --rm web python manage.py migrate
docker compose up -d
docker compose exec -T web python manage.py check --deploy
docker compose exec -T web python manage.py check_whatsapp
```

O proxy `edge-nginx` termina HTTPS, fixa os cabeçalhos encaminhados e alcança a aplicação pela rede Docker `gdnew_web`. Nenhuma porta do banco é publicada. A rede é compartilhada com o proxy existente para não reiniciar outros sistemas.

`scripts/publish_proxy.py` adiciona o domínio com backup da configuração e validação antes de recarregar o nginx. O certificado é renovado pelo mecanismo já usado em `/opt/edge/renew.sh`.

`scripts/backup.sh` cria um dump PostgreSQL em `/opt/financeiro-gd/backups`. O timer de sistema agenda uma cópia diária às 03h de Cuiabá (07h UTC). As cópias são locais; cópia externa e política de retenção devem ser definidas conforme a operação.

Antes de atualizar uma base com dados, execute o backup. Para restaurar em um ambiente separado, use `pg_restore` com o dump e valide a restauração antes de substituir a produção. O primeiro backup é validado com `pg_restore --list`.

## Acesso inicial

O comando `bootstrap_admin --password-file /caminho/privado` cria o administrador somente se ainda não existir, preservando uma senha já definida. A senha inicial deve ser alterada em **Minha conta**, clicando no nome do usuário no menu inferior.

## Comportamentos importantes

- O painel mostra saldos em aberto, não saldo bancário. O previsto mensal é a diferença entre contas a receber e a pagar ainda abertas.
- Alterações de recorrência podem valer para uma ocorrência ou próximas ocorrências sem baixa. O vencimento editado vale somente para a ocorrência atual.
- Contas com baixa não podem ser editadas ou canceladas. Vendas com recebimentos não podem ser canceladas. Estorno de baixas ainda não faz parte desta versão.
- O agendador roda a cada minuto. Resumos são enviados uma vez por dia após o horário escolhido. Se não houver pendências, registra isso sem enviar mensagem.
- Se a API não confirmar o envio, o sistema registra o resultado e não tenta novamente automaticamente naquele dia.
- Catálogos e vendas mostram até 200 registros; histórico mostra 150 atividades. Contas possuem paginação de 30 itens.

Referências: [segurança do Django](https://docs.djangoproject.com/en/5.2/topics/security/) e [Evolution API](https://github.com/EvolutionAPI/evolution-api).

## Importação de contas a pagar

`scripts/prepare_payables.py origem.xlsx destino.json` lê uma exportação de uma aba com openpyxl no ambiente de análise. O arquivo original não é alterado. Salve o JSON em `.private/`; planilhas e dados financeiros não devem entrar no GitHub.

`python manage.py import_payables arquivo.json --user email-do-admin` faz a simulação. Acrescente `--apply` para gravar após conferir os totais e executar um backup. A gravação é transacional: uma inconsistência desfaz o lote inteiro.

Contas `Confirmado` entram quitadas com a data de confirmação e um registro de baixa histórica. Contas `Atrasado` entram abertas. O valor da conta é o valor total líquido da exportação; descontos, juros, taxas, método de pagamento, competência e demais metadados são preservados nas observações e no registro original de importação. Nenhuma recorrência futura é inferida a partir de repetições históricas.

Cada registro recebe identificação da origem para impedir reimportação. Alterações em um registro já importado exigem revisão. Contas com mesma descrição e vencimento são sinalizadas nas observações; não são descartadas automaticamente quando possuem valores e identificações distintos.
