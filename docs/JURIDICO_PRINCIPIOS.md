# Jurídico — princípios permanentes

**A constituição do Workspace Jurídico.** Documento atemporal: não descreve telas, tabelas,
endpoints ou tecnologia. Se em cinco anos o SGC for reescrito do zero, este documento continua
valendo.

---

## Como usar este documento

Cada princípio tem um **código** (`M3`, `O5`, `I2`…). Use o código para confrontar uma proposta:
*"esse relatório viola U6"*, *"essa entidade não passa em E1"*. Um princípio citável é um
princípio que se aplica; um princípio genérico é decoração.

**Ordem de precedência.** Quando dois princípios colidirem — e vão colidir —, vale esta ordem:

1. **Fronteiras entre workspaces** (seção 2). Violar uma fronteira cria duplicidade permanente.
2. **Princípios de modelagem** (seção 3). Erros aqui contaminam tudo o que vier depois.
3. **Princípios operacionais** (seção 4).
4. **Usabilidade e escalabilidade** (seções 7 e 8).

**Cláusula de emenda.** Estes princípios podem ser alterados — o que não podem é ser ignorados
em silêncio. Mudar um princípio exige: registrar qual, por qual motivo, e o que passa a ser
verdade no lugar. Uma exceção pontual "só desta vez" não é emenda: é dívida, e cobra juros.

---

## 1. Propósito

> **O Jurídico existe para administrar o risco jurídico da empresa e a operação diária do
> contencioso — não para armazenar processos.**

Três consequências que decorrem diretamente dessa frase:

- **A unidade de gestão é o risco, não o processo.** O processo judicial é uma fase possível de
  um risco que começa antes dele e frequentemente termina depois.
- **O módulo serve a quem trabalha, todos os dias.** Se a equipe jurídica não abrir o sistema
  numa segunda-feira comum, ele falhou — por mais completo que seja o cadastro.
- **Prevenir vale mais que registrar.** Um pedido recorrente que gera uma correção na obra vale
  mais que dez relatórios sobre o passivo existente.

---

## 2. Responsabilidade — o que o Jurídico é e não é

### Do que o Jurídico é dono

- **A informação jurídica**: processos, partes, fases, prazos, decisões, acordos, bloqueios.
- **O ciclo operacional do contencioso**: o que precisa ser feito, por quem, até quando.
- **A avaliação de risco**: exposição estimada, classificação, concentração.
- **A história oficial de cada caso.**

### Do que o Jurídico **não** é dono

| Domínio | Dono | O Jurídico faz o quê |
|---|---|---|
| Vínculo empregatício, admissão, desligamento, verbas | **RH** | Referencia e congela o contexto no momento da abertura do caso |
| Movimento de caixa, títulos, baixas, conciliação | **Financeiro** | Origina obrigações e recebe a confirmação de pagamento |
| Escrituração, competência, resultado contábil | **Contabilidade** | Fornece a base de provisão; não escritura |
| Obras, contratos, centros de custo | **Projetos** | Referencia para atribuir o passivo à sua origem |
| Identidade, permissões, auditoria técnica | **Sistema** | Consome |

### As três frases que resolvem qualquer dúvida de fronteira

- **`R1` — O Jurídico não é RH.** Ele não cadastra colaborador, não calcula rescisão, não corrige
  desligamento. Se o dado de origem está errado, corrige-se no RH.
- **`R2` — O Jurídico não é Financeiro.** Ele não paga, não baixa título, não concilia banco. Ele
  diz *o que* deve ser pago, *quanto* e *quando*.
- **`R3` — O Jurídico não é Contabilidade.** Ele informa risco e provisão; a escrituração é de
  quem escritura.

> **Quando um dado pertence a outro workspace, o Jurídico referencia. Nunca copia — salvo o
> contexto congelado (§M8), que é exceção deliberada e documentada.**

---

## 3. Princípios de modelagem

**`M1` — A empresa administra riscos, não processos.**
O Caso é a unidade central. O processo judicial é uma fase dentro dele. Um caso pode existir sem
processo, e pode conter mais de um.

**`M2` — Um dado tem um único dono.**
Se dois lugares podem alterar a mesma informação, um deles está errado. Antes de criar um campo,
pergunte quem responde por ele quando divergir.

**`M3` — A Timeline registra apenas fatos consumados.**
Nunca previsões, nunca intenções, nunca compromissos futuros. Um fato tem data de ocorrência,
autor e procedência.

**`M4` — A Agenda registra apenas compromissos.**
Tudo o que tem data e ainda não aconteceu. Quando acontece, **vira fato** e passa para a
Timeline. Uma lista que mistura "vai acontecer" com "aconteceu" não serve para nenhuma das duas
leituras.

**`M5` — Estado é composto por eixos independentes, nunca por um campo único.**
Situação processual, financeira, de negociação e de bloqueio são dimensões distintas de uma
mesma realidade. Um campo tentando representar todas foi o defeito de origem do módulo, e a
tentação de recriá-lo volta a cada funcionalidade nova.

**`M6` — Eixo pequeno é eixo correto.**
Se um eixo precisa de mais de meia dúzia de valores, provavelmente está misturando duas
dimensões. O detalhe fino pertence à Timeline, não ao estado.

**`M7` — Casos representam fatos concretos.**
Um caso só nasce quando existe algo real: uma citação, uma notificação, um contato. Suspeita,
estatística e probabilidade não criam registro.

**`M8` — O contexto do risco é congelado, não consultado.**
Obra, centro de custo, gestor e motivo do desligamento são copiados no momento da abertura,
porque análise histórica exige o valor *da época*. É a única duplicação autorizada, e existe
justamente para não mentir sobre o passado.

**`M9` — Nada se apaga; tudo se reverte.**
Bloqueio liberado, acordo rompido, pagamento estornado, audiência remarcada: todos são fatos
novos que apontam o anterior. O passado é imutável.

**`M10` — Todo fato tem procedência e autor.**
Registro manual, carga inicial, publicação capturada ou integração: a origem é parte do fato.
É isso que permite confiar em números mistos e conviver com automação futura.

**`M11` — Estimativa e obrigação nunca se confundem.**
Valor da causa, valor de risco e valor devido são três coisas diferentes. Só a obrigação
formalizada vira compromisso financeiro.

**`M12` — Visão calculada não é entidade.**
Radar, ficha consolidada, ranking, concentração: são leituras sobre fatos existentes. Se pode ser
calculado, não deve ser armazenado — exceto por desempenho, e aí com dono único e recálculo
possível.

**`M13` — O sistema não inventa o que não sabe.**
Campo sem informação é exibido como "não informado". Inferir data, valor ou estado é criar
mentira com aparência de dado — e ela sobrevive por anos.

---

## 4. Princípios operacionais

**`O1` — O dia começa pela Central de Trabalho.**
Ela responde "o que eu preciso resolver hoje?". É a porta de entrada do módulo para quem opera.

**`O2` — A Central é uma fila executável, não um relatório de problemas.**
Se não pode ser esvaziada num dia normal de trabalho, deixou de ser fila. Lista que nunca zera é
lista que ninguém lê.

**`O3` — Todo item de trabalho tem dono.**
Alerta sem responsável é alerta de ninguém. A visão padrão de qualquer fila é pessoal; a visão da
equipe é uma escolha explícita.

**`O4` — Toda pendência tem saída.**
Concluir, reprogramar com motivo, repassar ou dar ciência por prazo determinado. O que não tem
saída acumula, e o que acumula é ignorado.

**`O5` — Silenciar é um recurso legítimo, esquecer não é.**
Adiamento tem prazo e motivo; nunca é permanente. Um item silenciado sempre volta.

**`O6` — A Timeline não se edita.**
Fato registrado errado é corrigido por um fato novo que o retifica, com autor e motivo. Reescrever
o passado destrói a única coisa que a Timeline oferece: confiança.

**`O7` — Compromisso se remarca, não se apaga.**
Audiência adiada três vezes é informação sobre o processo. A remarcação preserva o original e
vincula o novo.

**`O8` — A negociação termina no aceite; o acordo começa na formalização.**
Entre um e outro não há obrigação exigível — e, portanto, nada a cobrar, provisionar ou pagar.

**`O9` — Prazo perdido é falha do sistema, não do usuário.**
Se um prazo venceu sem que ninguém fosse avisado com antecedência útil, o defeito é do desenho
dos alertas. Essa é a métrica de qualidade mais importante do módulo.

**`O10` — Ausência de fato é informação.**
Um caso ativo sem nenhum registro há muito tempo não é um caso tranquilo: é um caso abandonado.
O silêncio precisa gerar sinal.

**`O11` — O Painel executivo é consultado, não operado.**
A diretoria lê e, no máximo, clica para investigar. Nenhuma decisão operacional depende de alguém
que entra no módulo uma vez por mês.

---

## 5. Princípios de integração

**`I1` — Cada workspace mantém o que é seu; o Jurídico referencia.**
Sem cópia, sem sincronização de cadastro, sem "espelho" de tabela alheia.

**`I2` — RH origina, Jurídico conduz.**
O desligamento pertence ao RH e é a origem do risco trabalhista. O Jurídico observa essa origem
para prevenir, mas não a administra nem a corrige.

**`I3` — Jurídico origina a obrigação, Financeiro executa o pagamento.**
O Jurídico diz o que deve ser pago, quanto e quando. O Financeiro paga, baixa e concilia. A
confirmação volta para o caso.

**`I4` — O Financeiro só recebe o que a empresa paga por vontade própria.**
Constrição judicial e estimativa não são contas a pagar. Bloqueio nunca vira título — se virasse,
a empresa pagaria duas vezes o mesmo valor.

**`I5` — Contabilidade recebe base, não lançamento.**
O Jurídico fornece risco e provisão por competência; a escrituração pertence a quem escritura.

**`I6` — Projetos recebem o passivo que originaram.**
Todo caso aponta a obra ou contrato de origem, para que o custo do contencioso volte ao lugar
onde a decisão foi tomada.

**`I7` — Relatórios consomem, nunca decidem.**
Relatório é extração; regra de negócio vive no módulo. Um número que só existe dentro de um
relatório é um número que ninguém consegue auditar.

**`I8` — Integração externa enriquece; nunca governa.**
Fonte externa — tribunal, provedor de publicações, qualquer automação futura — pode preencher
lacuna e propor fato novo. Não pode sobrescrever o que a operação registrou. Divergência vira
conflito para revisão humana, nunca sobrescrita silenciosa.

**`I9` — Depois da carga inicial, o SGC é a fonte oficial.**
A migração histórica é um marco encerrado. Nenhuma evolução futura pode reintroduzir dependência
de planilha ou de arquivo externo para manter o módulo atualizado.

---

## 6. Princípios de evolução

**`E1` — Antes de criar entidade, responda seis perguntas.**

1. Ela tem **ciclo de vida próprio** — nasce, muda e encerra por conta própria?
2. Ela **pertence a outro workspace**?
3. Pode ser apenas uma **visão calculada**?
4. Pode ser apenas um **filtro** sobre algo existente?
5. Pode ser apenas um **evento** ou um **fato** na Timeline?
6. Pode ser apenas uma **projeção de leitura**?

Se qualquer resposta de 2 a 6 for "sim", não crie a entidade.

**`E2` — "Seria elegante" é um não.**
Entidade não se cria por simetria conceitual, nem porque "um dia pode ser útil". Cria-se porque
existe uma pergunta operacional concreta que não tem resposta hoje.

**`E3` — Toda funcionalidade nova entra pelo Caso.**
Fato novo se registra no caso e aparece na Timeline. Funcionalidade que cria seu próprio centro
de gravidade fragmenta o módulo — em dois anos, ninguém sabe mais onde está a verdade.

**`E4` — Toda entidade compartilhada vira catálogo com visão própria.**
Nunca uma tabela solta pendurada num caso.

**`E5` — Extensão preferível a alteração.**
Um tipo novo, uma categoria nova, uma regra nova: o modelo deve crescer por acréscimo, não por
redesenho. Se uma necessidade nova exige quebrar um princípio, o problema é a necessidade ou o
princípio — e isso se discute, não se contorna.

**`E6` — Nova regra de alerta precisa de dono e de volume esperado.**
Regra sem destinatário não deve existir. Regra que dispara em grande parte do acervo está mal
calibrada e degrada todas as outras.

**`E7` — Nada entra sem saber como sai.**
Toda funcionalidade que cria registro precisa dizer como ele é encerrado, arquivado ou expira.
Sistema que só acumula fica insuportável no terceiro ano.

**`E8` — O que sobra é tão importante quanto o que entra.**
Revisar periodicamente o que ninguém usa é parte da manutenção. Funcionalidade morta ocupa
espaço, atenção e confiança.

---

## 7. Princípios de usabilidade

**`U1` — Toda informação precisa justificar seu espaço.**
Se ninguém age a partir dela, ela sai da tela.

**`U2` — Menus enxutos.**
Um menu que ninguém consegue ler inteiro é um menu que ninguém lê. Se algo é usado uma vez por
mês, pertence à Administração.

**`U3` — Não existem duas telas para a mesma pergunta.**
Duplicidade de tela produz duplicidade de verdade — e, mais cedo do que se espera, números
diferentes para a mesma coisa.

**`U4` — A ação acontece onde a informação está.**
Se resolver um item exige abrir três telas, o item não será resolvido.

**`U5` — Padrão pessoal, escopo explícito.**
Toda lista abre no recorte do usuário. Ver "tudo" é uma escolha consciente, nunca o padrão.

**`U6` — Todo número é clicável até o fato.**
Indicador do qual não se chega aos casos que o compõem é indicador em que ninguém confia.

**`U7` — Cada número sugere uma decisão.**
Se não muda nenhuma decisão, não é indicador: é curiosidade. Vira relatório ou desaparece.

**`U8` — Contexto vale mais que navegação.**
O que se precisa saber sobre um caso deve estar na tela do caso — não a três cliques de
distância.

**`U9` — Consistência acima de personalização.**
Telas padronizadas permitem que uma pessoa ajude a outra e que alguém novo produza na primeira
semana. Layout personalizável impede as duas coisas.

---

## 8. Princípios de escalabilidade

**`S1` — O que cresce é o fato, não o cadastro.**
Timeline, eventos, lançamentos e sinais crescem sem limite. O desenho deve assumir isso desde o
início, e não descobrir no terceiro ano.

**`S2` — Nenhuma tela pode depender de listar tudo.**
Busca, filtro e recorte são a forma de navegar. Rolagem infinita não é experiência: é ausência de
projeto.

**`S3` — Ação em lote é operação normal, não exceção.**
Redistribuir carteira, encerrar por prescrição, dar ciência em conjunto: com volume, tudo o que
se faz um a um deixa de ser feito.

**`S4` — Alerta escala pior que dado.**
Dobrar o acervo pode multiplicar os alertas por dez. Toda regra precisa de teto, dono e
monitoramento do próprio volume.

**`S5` — Preparado para automação, dependente de nenhuma.**
Captura de publicações, integração com tribunais, inteligência artificial: todas entram como
**fonte de fato**, sujeitas a `I8`. O módulo tem de funcionar plenamente sem qualquer uma delas.

**`S6` — Novos tipos entram por catálogo, não por reforma.**
Novo tipo de caso, de evento, de pedido, de restrição: acréscimo de dado, não mudança de
estrutura.

**`S7` — Múltiplos escritórios e múltiplas empresas são questão de escopo, não de cópia.**
Crescer em organizações atendidas nunca deve significar duplicar o modelo.

**`S8` — Dado pessoal tem prazo.**
O módulo acumula informação sensível de pessoas que já não têm relação com a empresa. Retenção e
anonimização são parte do desenho, não uma preocupação para depois — retroagir sobre dez anos de
histórico custa muito mais do que decidir agora.

---

## 9. Princípios de qualidade — o teste de aceitação

Uma funcionalidade só entra se passar em **todos** os itens:

| # | Critério | Pergunta de verificação |
|---|---|---|
| `Q1` | Resolve problema real | Qual pergunta operacional hoje sem resposta ela responde? |
| `Q2` | Não duplica informação | O dado já existe em outro lugar? Quem é o dono? |
| `Q3` | Respeita as fronteiras | Ela invade RH, Financeiro ou Contabilidade? |
| `Q4` | Não aumenta a complexidade sem necessidade | Passa nas seis perguntas de `E1`? |
| `Q5` | Melhora a operação diária | Alguém usa isso numa segunda-feira comum? |
| `Q6` | Tem dono e saída | Quem responde por ela? Como o registro encerra? |
| `Q7` | Escala | Continua utilizável com dez vezes mais dados? |
| `Q8` | Coerente com estes princípios | Qual princípio ela poderia estar violando? |

Se a resposta de `Q8` for "nenhum", a pergunta foi mal feita — vale reler com mais rigor.

---

## 10. Manifesto

> **O Workspace Jurídico da M&E**

**Administramos risco, não papel.**
O processo é uma fase; o risco começa antes e termina depois.

**O sistema é da operação.**
Se a equipe não abre numa segunda-feira comum, ele falhou — por mais completo que seja o cadastro.

**Um caso é uma história, não uma ficha.**
Tudo o que aconteceu está em uma linha do tempo, na ordem em que aconteceu, com autor e origem.

**O passado é imutável.**
Nada se apaga. Corrige-se com um fato novo, para que a história continue verdadeira.

**O futuro mora na agenda.**
Compromisso é compromisso; fato é fato. Confundi-los estraga as duas leituras.

**Cada dado tem um dono.**
O RH é dono do vínculo. O Financeiro é dono do caixa. A Contabilidade é dona da escrituração.
Nós somos donos da informação jurídica — e só dela.

**Estado é composto, não único.**
Onde está no rito, o que devemos e como negociamos são perguntas diferentes. Um campo só para
todas foi o nosso defeito de origem; não voltaremos a ele.

**Não inventamos o que não sabemos.**
"Não informado" é uma resposta honesta. Dado inferido é mentira com aparência de verdade.

**A fila precisa poder ser esvaziada.**
Uma lista que nunca zera é uma lista que ninguém lê. Alerta sem dono é alerta de ninguém.

**Todo número precisa sugerir uma decisão.**
O resto é curiosidade, e curiosidade não ocupa tela.

**Automação enriquece; nunca governa.**
Tribunal, publicação, inteligência artificial: entram como fonte de fato, sujeitas à conferência
humana. O sistema funciona sem elas.

**Prevenir vale mais que registrar.**
Um pedido recorrente que vira correção na obra vale mais que dez relatórios sobre o passivo que
já existe.

**Simples de operar, difícil de inchar.**
Toda funcionalidade nova entra pelo caso, tem dono, tem saída e cabe nos princípios acima.
Quando não couber, discutimos o princípio — não o contornamos.

---

*Encerrada a fase de concepção do Workspace Jurídico. A partir daqui, implementação das fases
definidas em [`JURIDICO_ESPECIFICACAO.md`](JURIDICO_ESPECIFICACAO.md).*
