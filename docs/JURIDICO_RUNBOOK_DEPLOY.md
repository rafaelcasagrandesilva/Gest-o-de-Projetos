# Runbook — deploy do Workspace Jurídico em produção

Procedimento definitivo da primeira subida. Tempo estimado: **15 a 20 minutos**, dos quais a
importação leva poucos segundos.

Ao final, a produção fica idêntica ao ambiente de testes: **159 desligados e 146 processos**,
passivo considerado de **R$ 5.858.532,41** (verificado por comparação campo a campo entre um banco
importado do zero e o ambiente de testes — 0 divergências).

> **Leia antes:** o painel HTML é usado **somente nesta primeira carga**. Todas as atualizações
> seguintes usam apenas a planilha. Ver [`JURIDICO_IMPORTACAO_PLANILHA.md`](JURIDICO_IMPORTACAO_PLANILHA.md).

## Antes de começar

- [ ] Planilha oficial em mãos (`PLANILHA UNIFICADA - PROCESSOS E DEMITIDOS 2.xlsx`)
- [ ] `painel_passivo.html` em mãos (só desta vez)
- [ ] Um usuário de produção com perfil ADMIN ou GESTOR (precisa de `legal_imports.create`)
- [ ] Janela combinada — o `alembic upgrade` roda migrations pendentes de outros módulos também

---

## 1. Backup do banco

```bash
DATABASE_URL="postgresql://usuario:senha@host:5432/banco" BACKUP_DIR=/backup/sgp ./scripts/backup_postgres.sh
```

- [ ] O arquivo foi gerado e tem tamanho compatível com o do banco (não é um dump de 0 byte).

Este é o ponto de retorno de todo o procedimento. Não avance sem ele.

## 2. Deploy do código

Publique a versão nova (backend + frontend) pelo processo habitual e confirme que o serviço
subiu.

- [ ] A aplicação responde e a versão publicada é a esperada.

## 3. Migrations

```bash
alembic upgrade head
```

Deve terminar em `0117_legal_import_runs`. Confira:

```bash
alembic current
```

O que essas migrations fazem no Jurídico: criam as tabelas **vazias**, registram as permissões do
módulo e criam a tabela do histórico de importações. São aditivas — nenhum dado existente é
alterado.

- [ ] `alembic current` retorna `0117_legal_import_runs`.
- [ ] O Workspace Jurídico aparece no menu para o usuário ADMIN, com as telas vazias.

> Se este for um banco **novo**, o `upgrade head` roda a cadeia inteira. Isso hoje funciona porque
> o Alembic confirma uma transação por migration (`transaction_per_migration`); sem isso, uma
> migration antiga que cria um valor de enum e outra, adiante, que o utiliza fariam a subida
> falhar no meio.

## 4. Abrir a tela de importação

Workspace Jurídico → **Administração** → aba **Importações**.

- [ ] A aba abre e o histórico está vazio ("Nenhuma importação executada ainda").

## 5. Selecionar os arquivos

- **Planilha consolidada (.xlsx)** → a planilha oficial
- **Painel de Passivo (.html)** → `painel_passivo.html` — **somente nesta primeira carga**

- [ ] Os dois arquivos aparecem selecionados, com nome e tamanho.

## 6. Analisar e conferir a pré-visualização

Clique em **Analisar arquivos**. Nada é gravado nesta etapa.

Números esperados na carga inicial:

| Indicador | Esperado |
| --- | --- |
| Linhas lidas | 186 |
| Novos desligados | 159 |
| Novos processos | 146 |
| Atualizados | 0 |
| Duplicados | 25 (linhas repetidas que a carga consolida — normal) |
| Erros | **0** |
| Avisos | 9 (1 data digitada errada na planilha + 8 números fora do padrão CNJ) |
| Linhas ignoradas | 3 (reclamante "Desconhecido") |
| Painel | 134 de 185 entradas vinculadas |

- [ ] **Erros = 0.** Se houver erro, **não confirme**: abra a lista, corrija a planilha e analise
      de novo.
- [ ] Os números batem com a tabela acima (numa carga futura, o esperado é outro — o que importa é
      que o resumo faça sentido).

## 7. Confirmar a importação

Clique em **Confirmar importação**. O relatório final aparece com as mesmas categorias, agora do
que foi efetivamente feito, e uma linha nova entra no histórico ao pé da página.

- [ ] Relatório mostra "Importação concluída".
- [ ] O histórico registra a carga com seu usuário, os dois arquivos e o tempo de execução.

## 8. Validação rápida

| Tela | O que conferir |
| --- | --- |
| **Dashboard Executivo** | Passivo considerado **R$ 5.858.532,41**; gráficos por status/UF preenchidos |
| **Processos** | 146 registros; abrir um e ver valores, foro, cidade e o link do JusBrasil |
| **Desligados** | 159 registros; abrir uma ficha e ver os processos vinculados |
| **KPIs** | Contagem de processos e de pessoas coerente com a lista (aplicar um filtro e ver os cards acompanharem) |
| **Relatórios** | Gerar o Excel do Jurídico e conferir se as abas vêm preenchidas |

- [ ] Um usuário **sem** `legal_cases.sensitive` não enxerga valores (confira com um perfil
      CONSULTA, se houver).

## Se algo der errado

| Situação | O que fazer |
| --- | --- |
| Pré-visualização com erros | Não confirme. Corrija a planilha e analise de novo — nada foi gravado. |
| Importou com o arquivo errado | Os registros criados podem ser **desativados** em Administração (baixa lógica). Para desfazer em massa, restaure o backup do passo 1. |
| Números divergem do esperado | Confira se enviou o painel junto. Sem ele a carga inicial fica sem valores. |
| `alembic upgrade` falhou no meio | O banco fica na última migration bem-sucedida. Corrija a causa e rode de novo — não é preciso restaurar. |

---

## Depois desta carga: as próximas atualizações

Quando a consultoria enviar uma versão nova da planilha:

1. Administração → Importações
2. Selecionar **apenas a planilha** — o painel não é mais necessário
3. Analisar, conferir, Confirmar

O importador cria os processos novos, atualiza os que mudaram e **preserva** tudo o que o painel
enriqueceu na primeira carga (valor considerado, valor da causa, link do JusBrasil, foro, cidade,
natureza, última movimentação e reclamado). Campo vazio nunca apaga informação existente, e
registro que sumiu da planilha continua no sistema.

Não é preciso nova migration, script ou seed.
