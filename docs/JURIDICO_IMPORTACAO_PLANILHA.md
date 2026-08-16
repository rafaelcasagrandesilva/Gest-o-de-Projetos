# Jurídico — a planilha como forma oficial de alimentar o módulo

A carga do Workspace Jurídico é feita **importando a planilha** pela tela
(Administração → Importações). Não há seed em produção: o ambiente sobe vazio e a primeira
importação o preenche.

## O ciclo de vida da carga

```
1ª carga     planilha.xlsx + painel_passivo.html  ──→  banco ENRIQUECIDO
                                                        (valores, links, foro, cidade…)

daqui em     planilha.xlsx                        ──→  cria os novos,
diante       (só ela)                                  atualiza o que mudou,
                                                       PRESERVA tudo o que veio do painel
```

**O painel é fonte HISTÓRICA, não dependência do módulo.** Ele existe para enriquecer a primeira
carga. Depois disso os metadados pertencem ao banco, e as sincronizações seguintes usam apenas a
planilha. Se o arquivo do painel nunca mais existir, nada deixa de funcionar.

## Um único fluxo de transformação

```
planilha .xlsx  ─┐
                 ├─→  legal_import_parser.build_payload()  ──→  LegalImportService
painel .html  ───┘         (transformação)                     .preview()  → o que mudaria
   (1ª carga)                                                  .apply()    → grava
```

| Camada | Arquivo | Papel |
| --- | --- | --- |
| Transformação | `app/services/legal_import_parser.py` | Lê as fontes, valida o formato, normaliza |
| Carga | `app/services/legal_import_service.py` | Compara com o banco, pré-visualiza e grava |
| API | `POST /legal/imports/preview` · `/confirm` · `GET /legal/imports` | Multipart; `legal_imports.create` |
| Tela | Administração → Importações | Analisar → conferir → Confirmar → histórico |
| Dev | `python manage.py seed_legal --xlsx … --painel …` | Só chama `apply()` — sem lógica própria |
| Dev | `scripts/build_legal_seed.py` | Gera um JSON LOCAL (não versionado) para atalho de dev |

Quem importa pela tela, quem roda o seed e quem gera o JSON executam **o mesmo código**.
Por isso o resultado é o mesmo nos três caminhos.

> **Dado pessoal não é versionado.** `app/scripts/data/` está no `.gitignore`: o JSON de seed
> carrega CPF, nome, rescisão e FGTS de pessoas reais. Produção nunca precisa dele — a carga é a
> importação da planilha.

## As quatro regras da carga

### 1. Inclui e atualiza — nunca exclui

Registro que sumiu da planilha **permanece** no sistema. Excluir continua sendo uma ação manual
(baixa lógica) do Workspace, e um processo desativado na tela **não volta** numa reimportação.

### 2. Campo vazio nunca sobrescreve informação existente

Só valores presentes na fonte são gravados. Isso também protege o que foi ajustado na tela em
colunas que a planilha não preenche — inclusive o status: célula em branco não desfaz um status
alterado manualmente (o padrão "Em andamento" só vale na criação).

### 3. Os dados enriquecidos são preservados automaticamente

Numa importação **sem o painel**, estes campos do processo não são reescritos de forma alguma:

| Campo | |
| --- | --- |
| `jusbrasil_url` | Link JusBrasil |
| `amount_claimed` | Valor da causa |
| `amount_considered` | Valor considerado |
| `court` | Foro |
| `city` | Cidade |
| `nature` | Natureza |
| `last_movement` / `last_movement_date` | Última movimentação |
| `defendant_name` | Reclamado |

A regra é mais forte que "vazio não apaga": a planilha **não empobrece o banco** nem quando tem um
valor a oferecer. `defendant_name` é o exemplo concreto — sem o painel ele cairia para a coluna
"Empresa Reclamada", que em ~25 processos registra a concessionária tomadora em vez da parte real.

**Empresa** (`company`) é coluna da planilha e continua atualizável, com uma exceção: sem o painel,
a planilha não troca uma entidade do grupo M&E (que só o painel identifica, em 2 processos) pela
concessionária. Se precisar corrigir esses casos, edite em Administração → Processos ou importe
com o painel junto.

Numa **criação** não há o que preservar: o registro novo aproveita tudo o que a planilha oferece.

### 4. A importação é idempotente

Chave natural: CPF (ou nome, quando não há CPF) para a pessoa e número do processo para o
processo. Reimportar o mesmo arquivo **não cria nada e não altera nada** — verificado contra a
base real, com e sem o painel.

Casos de borda tratados: pessoa repetida em várias linhas vira um cadastro; número de processo
repetido vira um processo (prevalece a linha com reclamante identificado); reclamante
"Desconhecido" gera o processo sem pessoa vinculada; homônimos sem CPF **não** são atualizados no
escuro — viram um conflito relatado.

## Formato oficial

O cabeçalho é o contrato: aba ou colunas diferentes param a importação com uma mensagem dizendo
o que se esperava. A comparação ignora acento, caixa, pontuação e as variações de "Nº" (`N°`,
`N.`, `N`), e **colunas novas ao final são aceitas** — a planilha pode crescer.

## Pré-visualização e relatório

`Analisar` roda a importação inteira em modo simulação (nada é gravado) e mostra novos,
atualizados, duplicados, linhas ignoradas, erros e avisos — com a lista de quem é cada um e,
nas atualizações, **quais campos** mudam. `Confirmar` repete a operação gravando e devolve o
mesmo relatório, agora do que foi feito.

O relatório nunca exibe VALORES, só nomes de campo — assim não depende de Dados sensíveis.

## Histórico de importações

Cada importação **confirmada** grava uma linha em `legal_import_runs`, listada na própria aba:
data e hora, usuário, arquivos, linhas lidas, novos e atualizados (desligados e processos), sem
alteração, ignorados, duplicados, erros, avisos e tempo de execução. Pré-visualizações não geram
registro. O registro vai na mesma transação da carga — "importação sem histórico" é um estado
impossível. O evento também é gravado em `audit_logs` (`entity = 'legal_import'`).

## Permissões

| Código | O que abre |
| --- | --- |
| `legal_imports.list` | Ver a aba Importações e o histórico |
| `legal_imports.create` | Pré-visualizar e executar a importação (implica `list`) |

Recurso próprio porque Importações é um MENU e porque importar escreve em Processos **e** em
Desligados de uma vez. Criado pela migration `0116` para quem já administra o módulo (tem
`legal_cases.create` **e** `legal_persons.create`) e para perfis com `system.admin`. Perfis
somente-leitura, como CONSULTA, não recebem nada.

## Deploy

Ver [`JURIDICO_RUNBOOK_DEPLOY.md`](JURIDICO_RUNBOOK_DEPLOY.md).
