# Etapa 0 — Agenda do workspace Projetos

**Objetivo:** uma agenda onde a gestão marca reuniões e **atribui obrigações a responsáveis com
prazo**, e onde a ata da reunião fica anexada ao próprio compromisso.

**Princípio inegociável (decisão do usuário):** a agenda de Projetos é **totalmente separada** da
agenda do Jurídico. Nenhum registro de uma aparece na outra, as opções de cada uma são próprias,
e **nada no módulo Jurídico é alterado**. A agenda do Jurídico serviu apenas de referência visual.

> Status: **Etapa 0 — desenho para confirmação.**

---

## 1. O que precisa resolver

Dois usos, que o mesmo registro atende:

**Obrigação atribuída** — *"João Martins precisa trazer a resposta da Vilela Advogados até
sexta-feira que vem."* Tem responsável, prazo e a explicação do que se espera. Alguém entrega e
marca como cumprido.

**Reunião** — *"quarta-feira, reunião de gestores com Luciano, Sigmar, João Martins, Paulo e
Rafael, às 10h, na sede."* Tem horário, local, vários participantes — e, depois, **a ata**.

O que amarra os dois: **data, gente e cobrança**. Sem cobrança a agenda vira um calendário que
alguém precisa lembrar de abrir; por isso o acompanhamento (§4) faz parte do escopo, não é extra.

## 2. Descoberta que simplifica o desenho

**As cinco pessoas citadas já são usuários do SGC** — João Carlos Martins, Luciano Ribeiro de
França, Paulo Arieiro, Sigmar Dupre Guimarães e Rafael Casagrande. Responsável e participantes
podem então ser **vínculo real com `users`**, e não texto: é isso que permite cada um abrir o
sistema e ver o que lhe foi atribuído.

Para quem não tem login (Vilela Advogados, um cliente, um colaborador sem acesso) existe um campo
livre **participantes externos** — decisão do usuário, e evita inventar cadastro de contato.

## 3. Modelo de dados (tudo novo, nada compartilhado)

### `project_commitments` — o compromisso

| Campo | Observação |
|---|---|
| `kind` | REUNIAO · OBRIGACAO · EVENTO · PRAZO · VISITA — **opções próprias da agenda de Projetos** |
| `title` | "Reunião de gestores", "Resposta da Vilela Advogados" |
| `description` | o que se espera; texto livre |
| `starts_at` | data e hora do compromisso (reunião/evento) |
| `due_at` | prazo limite (obrigação). Um dos dois basta |
| `all_day` | compromisso sem hora marcada |
| `location` / `modality` | local e PRESENCIAL · VIRTUAL · HIBRIDA |
| `project_id` | projeto relacionado — **opcional** (reunião de gestores pode não ter projeto) |
| `owner_user_id` | **responsável**: quem responde pela entrega |
| `external_participants` | texto livre, para quem não tem login |
| `status` | AGENDADO · CONCLUIDO · CANCELADO · ADIADO |
| `completed_at` / `completion_note` | quando e com que observação foi concluído |
| `created_by_id` | autoria |

### `project_commitment_participants` — quem participa

`(commitment_id, user_id)`. O responsável entra automaticamente como participante.

### `project_commitment_attachments` — a ata e outros documentos

Metadados no banco, arquivo no volume sob `STORAGE_ROOT`, como os PDFs de NF e os comprovantes.
Cada anexo com **Ver** (abre no navegador) e **Baixar**, pela regra única já existente.

> A ata é anexo hoje. Quando o sistema gerar a ata sozinho, ela nasce como mais um anexo do mesmo
> compromisso — o modelo não muda.

## 4. Acompanhamento (decisão do usuário)

- **Filtro "só os meus"** na agenda: mostra o que a pessoa responde ou participa
- **Contadores** de *atrasados* e *desta semana*, para o responsável e para quem coordena
- **Concluir** com observação — é o que fecha o ciclo da obrigação atribuída

Sem e-mail nesta etapa: o SGC não envia e-mail hoje, e ligar isso é bloco de trabalho próprio.

## 5. Telas

Menu **Agenda** dentro do workspace Projetos, com as mesmas três visões que a equipe já conhece
(**Mês · Semana · Lista**) — construídas para esta agenda, sem tocar no componente do Jurídico.

- **Mês/Semana**: compromissos no dia, com cor por tipo e marca de atrasado
- **Lista**: próximos N dias, agrupada por dia, com responsável e prazo visíveis
- **Modal de compromisso**: os campos do §3, seleção múltipla de participantes, anexos
- **Concluir** direto do detalhe

## 6. Permissões

Recurso próprio, um por menu, como manda o modelo do projeto:
`project_agenda.list / .read / .create / .update / .delete`, sob `workspace.projects.access`.

Quem tem acesso ao workspace enxerga a agenda; criar e atribuir exige `.create`/`.update`.

## 7. O que NÃO entra nesta etapa

- E-mail e notificação push
- Geração automática de ata
- Recorrência (reunião toda quarta) — cadastra-se uma a uma por enquanto
- Integração com calendário externo (Google/Outlook)

## 8. Riscos

| # | Risco | Mitigação |
|---|---|---|
| R1 | Virar "mais um lugar para esquecer de olhar" | O filtro "só os meus" e os contadores de atraso são o que dá vida ao registro — por isso estão no escopo |
| R2 | Confusão com a agenda do Jurídico | Dados, opções, permissões e telas separados; nada compartilhado |
| R3 | Anexo se perder no deploy | Grava sob `STORAGE_ROOT`, como NFs e comprovantes |
