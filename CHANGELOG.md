# Changelog — SGC

Histórico de mudanças do Sistema de Gestão Corporativa, do estado estável inicial
(abril/2026) até hoje. Cada entrada aponta o commit correspondente.

O que **existe hoje** no sistema está em
[`docs/SGC_DOCUMENTACAO_COMPLETA.md`](docs/SGC_DOCUMENTACAO_COMPLETA.md); este arquivo
registra apenas **o que mudou e quando**.

Formato: agrupado por mês, com o tipo da mudança em destaque
(**Novo** = funcionalidade nova · **Mudança** = comportamento alterado ·
**Correção** = defeito corrigido · **Interno** = sem efeito visível na tela).

---

## Agosto/2026

### Colaboradores, Relatórios e Indicadores (29/08 e 28/08)

- **Mudança — Colaboradores virou uma relação de cadastro** (`21f4c07`). Saíram os blocos
  Resumo da competência, Custos da competência, o alternador Previsto/Realizado e o
  seletor de Competência; esses consolidados já existem no Dashboard do projeto e no
  Contas a Pagar. Entraram: filtro por **Centro de Custo** (no lugar do filtro por
  projeto, porque há centros que não são projeto — Administrativo, Financeiro, TI),
  filtro de **Situação** (ativos / não ativos / todos), coluna com **todos os centros**
  do colaborador (cadastro + alocações ativas) e cards de Cadastrados, Situação e
  Vínculo CLT × PJ, com gráfico de distribuição por centro. Vínculo e gráfico contam
  apenas ativos.
- **Correção — o filtro por projeto em Colaboradores não filtrava nada** (`21f4c07`).
  Ele era enviado apenas para a busca da folha; a tabela de cadastro nunca o recebia.
- **Correção — relatórios do Financeiro sumiam para perfis novos** (`fcf2960`). O
  catálogo da tela filtrava por códigos legados (`invoices.view`), mas os perfis criados
  no modelo por verbos só têm `invoices.read` — o mesmo código que o backend exige. Quem
  tinha permissão via a lista vazia enquanto a API autorizava normalmente.
- **Novo — Evolução Financeira ganhou custo total e modo Contas a Pagar** (`c6aafae`).
  A série passa a usar o custo total do projeto (mão de obra + veículos + sistemas +
  fixos + impostos + rateio + antecipação). O modo CAP troca a origem do custo pelos
  títulos lançados e força a visão da empresa inteira, porque a maior parte do CAP é
  corporativa.

### Armazenamento de arquivos (28/08)

- **Correção — anexos sumiam a cada redeploy** (`23d5429`). Só o diretório dos PDFs de NF
  apontava para o volume persistente; documentos de projeto e anexos de ativos ficavam no
  disco efêmero do container. Agora existe uma raiz única (`STORAGE_ROOT`) da qual todos
  os diretórios derivam, o startup registra em log onde cada tipo está sendo gravado e
  alerta quando o caminho é efêmero em produção.
- **Novo — relatório de arquivos ausentes**. Em Configurações, lista os anexos que existem
  no cadastro mas cujo arquivo não está no servidor — é o que precisa ser reenviado.
  Também disponível como endpoint (`/admin/storage/missing-files`) e script de linha de
  comando.
- **Mudança — a tela passa a mostrar a causa real da falha de download**. O corpo de erro
  vinha como Blob e o motivo era descartado, virando sempre "não foi possível baixar".

### Contas a Pagar e Inicializar Competência (28/08)

- **Correção — quatro defeitos relatados pelo financeiro** (`1aee50f`): título pago
  voltando para em aberto na sincronização da mão de obra; título pago ganhando uma cópia
  em aberto ao lado quando o nome do colaborador era corrigido (o casamento era pelo
  nome); valor digitado na grade de Custos Fixos ficando sem título quando a vigência do
  item não cobria a competência; e a Inicializar Competência descartando em silêncio o
  colaborador multi-contrato, porque o teto de 100% ignorava as alocações independentes.
- **Correção — geração do CAP abortava o mês inteiro** (migration `0119`). Uma nota de
  286 caracteres em componente variável estourava o limite de 255 da coluna e derrubava a
  competência toda com erro de truncamento.
- **Novo — exclusão em massa nas quatro abas de custos do projeto** (`3ba7d11`), com
  prévia em duas fases: antes de excluir, o sistema informa quantos itens já têm pagamento
  lançado no Contas a Pagar.
- **Correção — despesa avulsa quebrava depois de gravar** (`1d56237`) e **evento de
  liquidação de antecipação falhava sem data de pagamento** (`a9591fb`). Mesmo defeito
  (nome ausente no escopo do handler) em dois módulos; o segundo foi encontrado pela
  varredura estática criada junto com o primeiro.

### Workspace Jurídico e Alocações (15/08)

- **Novo — Workspace Jurídico** (`f7854e7`): processos, pessoas, empresas e projetos do
  contencioso, com dashboard, relatório próprio e importação pela planilha oficial (a
  planilha inclui e atualiza, nunca exclui). Permissões próprias por menu.
- **Novo — Alocações multi-contrato** (`f7854e7`). Um colaborador pode atuar em mais de um
  contrato, com remuneração **independente** (padrão) ou por **rateio** — o que destravou
  o teto de 100% que bloqueava o multi-contrato.

### Antecipações (04/08 a 08/08)

- **Novo — Liquidação de NFs e ledger de repasse** (`b7ea2e8`, `fe95568`): liquidação
  parcial e multi-origem, retirada de repasse, liquidação em massa, histórico de eventos e
  relatório consolidado de Operações e Liquidações. O repasse saiu do Contas a Pagar e
  passou a um livro append-only.
- **Mudança — editar operação sem o passo "Confirmar"** (`81e4cb6`): criar já ativa a
  operação, e a edição reverte, reaplica e recalcula.
- **Novo — Cronograma Financeiro personalizado no Endividamento** (`a5b8d6d`): o
  cronograma passa a ser a fonte oficial das parcelas, pagas pelo CAP.
  Correções relacionadas em `e63afda` e `c67dd13`.

### Ajustes de interface (17/08 e 30/07)

- **Mudança — alinhamento contábil dos valores e faixas fixas nos cards** (`f172f4e`).
- **Mudança — "NF Oficial/Não Oficial" virou "Faturado/Pré-Faturado"** (`f16f640`).

---

## Julho/2026

- **Novo — Componentes Variáveis de Pagamento e múltiplos lançamentos por competência em
  Custos Fixos** (`883f205`, `145d3b0`). Benefícios e ajudas de custo passam por um
  pipeline único até o Contas a Pagar e o relatório, e um mesmo custo fixo pode ter vários
  lançamentos no mesmo mês.
- **Novo — Dados Sensíveis, Dashboard Financeiro e filtro por Centro de Custo**
  (`939e685`, `1959f75`): separa "acessar o módulo" de "ver valores financeiros"; o
  Dashboard Financeiro ganhou recurso próprio em vez de reaproveitar a permissão de
  faturamento, que vazava valores.
- **Novo — perfis de usuário administráveis** (`3cd2fce`, migration `0091`): os perfis
  passam a viver no banco (`role_permissions`), com vínculo vivo por deltas.
  `59dd197` liberou a exclusão de perfis sem usuários, e `ce55693` corrigiu o efetivo
  exibido na sessão.
- **Novo — histórico temporal de Centro de Custo** para colaboradores e veículos
  (`f697fc6`) e **serviço central único de Centros de Custo** (`45c9754`), que corrigiu o
  caso do centro "Drone".
- **Novo — Centro de Custo próprio do projeto** (`112827a`, `be4b385`), habilitando o
  filtro de Mão de Obra (`6d2aaa0`).
- **Mudança — isolamento de permissões por módulo** (`80edfaa`): Endividamento, CAP,
  Recebíveis e Relatórios passam a usar cada um o seu par de permissões.
- **Mudança — a navegação inicial do workspace vai para a primeira tela permitida**
  (`9f07084`), e a tela de Colaboradores foi reorganizada em drawer e seções recolhíveis
  (`cdca773`).
- **Correção — a grade mensal voltou a governar o valor da competência no CAP**
  (`1f8e5b3`); a geração automática de Custos Fixos/Endividamento deixou de retroagir
  (`5a144b7`).
- **Marco — release v1.0.0**, publicação do estado em produção (`a39170f`), precedida do
  endividamento por colaborador (`307cd35`).

---

## Junho/2026

- **Novo — Dashboard Operacional** e melhorias financeiras (`df2b135`).
- **Novo — reconciliação de snapshots do Contas a Pagar** e tratamento de lançamentos
  obsoletos (`15ca057`).
- **Mudança — reestruturação da densidade visual** dos dashboards e da interface em geral
  (`59c2f7d` como ponto de restauração, `054a4df` na fase 2 e `56080eb` na fase 3).
- **Mudança — deságio e tarifa de borderôs preservados no CAP** (`8abd7d6`); retenção
  desconsiderada no gráfico (`d0b5e5d`).

---

## Maio/2026

- **Novo — módulo de Gestão de Ativos** (`ad86016`) e, na sequência, **EPIs e melhorias
  patrimoniais** (`2224ed3`), com validação de devolução (`3d563dc`).
- **Novo — relatórios operacionais, financeiros e patrimoniais** (`1ca3dc8`).
- **Novo — override mensal da folha CLT** (`0a7da89`).
- **Novo — sistema estruturado de Centros de Custo** (`cc0585c`) e edição estrutural do
  financeiro corporativo (`3a595d6`, `6e8b0bb`).
- **Mudança — sincronização de custos diversos e sistemas com o Contas a Pagar**
  (`39aa320`), com ajustes de competência e nomenclatura (`f20dae1`) e limpeza de itens
  apagados (`f006ef2`).
- **Correção — geração de contas a pagar e separação financeira do CLT** (`c598c34`),
  tipo do título de endividamento (`30aec8d`), permissão de faturamento (`e48f714`),
  invalidação de sessão e sincronia de workspace (`fa34176`, `f55353d`).

---

## Abril/2026

- **Marco — versão estável do sistema completo** (`08dd710`) e primeiro deploy em produção
  no Railway (`bc4fd65` e a sequência de ajustes de CORS, proxy HTTPS, rotas com barra
  final e porta dinâmica).
- **Novo — sistema de auditoria com exportação** (`f06a233`, `db2b40d`).
- **Novo — permissões de usuários** (`38e1485`, `c86aa6e`, `5510c7f`) e visão global do
  dashboard por vínculo com todos os projetos (`7b9ac2d`).
- **Novo — custo por competência e override de custo** (`08de4c8`, `497dbc6`).

---

## Como manter este arquivo

Ao concluir uma mudança, acrescente uma linha na seção do mês corrente antes de commitar.
Prefira descrever **o efeito para quem usa o sistema** e, quando for correção, **o sintoma
que existia** — é isso que torna o histórico útil meses depois. O hash do commit entra
entre parênteses no fim.
