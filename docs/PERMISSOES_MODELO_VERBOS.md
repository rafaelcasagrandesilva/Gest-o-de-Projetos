# Modelo de permissões por verbos — referência

> Complementa `SGC_MATRIZ_PERMISSOES_DEFINITIVA.md` (matriz legada) e
> `SGC_ARQUITETURA_PERMISSOES_FUTURAS.md`. Este documento é a referência do **modelo de verbos**
> introduzido na **Etapa 0** (infraestrutura). Fonte de verdade no código:
> `app/core/permission_codes.py` (`PERMISSION_SPECS`, `PERMISSION_IMPLIES`, `ACTIVE_PERMISSION_CODES`).

## 1. Conceito

Cada permissão é `<recurso>.<capacidade>`, em **dois eixos ortogonais**:

- **Verbo** (o que se faz): `reference` < `list` < `read` < `create` / `update` / `delete`.
- **Sensibilidade** (quais campos se recebe): `<recurso>.sensitive` (bundle). No futuro,
  campos granulares (`<recurso>.salary`, `<recurso>.documents`, `projects.margin`, …) apenas
  acrescentam nós ao grafo — **sem redesenho**.

Nomes internos usam `read`/`update` (não `view`/`edit`) para **não colidir** com os códigos legados
`<recurso>.view`/`<recurso>.edit`, preservando 100% da compatibilidade. Na interface, o
administrador vê apenas os rótulos em pt‑BR (Referenciar, Listar, Visualizar, Criar, Editar,
Excluir, Dados sensíveis).

## 2. Hierarquia (grafo `PERMISSION_IMPLIES`)

Cadeia de verbos (o mais forte concede o mais fraco):

```
update ⇒ read ⇒ list ⇒ reference        delete ⇒ read
create ⇒ reference                        (create/update ⇒ cost_center.reference)
```

`sensitive` é independente (bundle). Aliases legados (compatibilidade — resolvidos em código, sem
tocar `user_permissions`):

| Código legado | Implica (códigos novos) |
|---|---|
| `employees.view` | `employees.read` (→ list → reference) · `employees.sensitive` · `cost_center.reference` |
| `employees.edit` | `employees.create` · `employees.update` · `employees.delete` · `employees.sensitive` |
| `assets.view` | `assets.read` (→ list → reference) · `assets.sensitive` · `cost_center.reference` |
| `assets.edit` | `assets.create` · `assets.update` · `assets.delete` · `assets.sensitive` |
| `vehicles.view` | `vehicles.read` (→ list → reference) · `vehicles.sensitive` · `cost_center.reference` |
| `vehicles.edit` | `vehicles.create` · `vehicles.update` · `vehicles.delete` · `vehicles.sensitive` |
| `projects.view_list` / `company_finance.view` | `cost_center.reference` |

## 3. Catálogo dos códigos novos (Etapa 0)

**Status = Inativo** em todos: já existem no banco e na grade de administração, mas **não entram na
sessão do frontend nem são checados por endpoint** até a etapa do respectivo módulo. Os campos
*Endpoints* / *Telas* abaixo descrevem o uso **planejado** (a etapa que os ativará).

| Código | Descrição | Implicado por (legado) | Endpoints (planejado) | Telas (planejado) | Etapa |
|---|---|---|---|---|---|
| `employees.reference` | Usar colaborador em seletor (id + nome), sem abrir Colaboradores | `employees.view`, `employees.edit`* | `GET /collaborators/search`, `GET /collaborators/cost-centers` | `CollaboratorSelect` (picker em Ativos), `AssetDetail` | E2 |
| `employees.list` | Listar colaboradores **sem** campos sensíveis | `employees.view` | `GET /collaborators`, `GET /hr/employees` | `Employees` (grid) | E1 |
| `employees.read` | Ver detalhe do colaborador **sem** sensíveis | `employees.view` | `GET /hr/employees/{id}` (detalhe) | `Employees` (drawer) | E1 |
| `employees.create` | Inserir novo colaborador | `employees.edit` | `POST /hr/employees`, `POST /employees` | Botão "Inserir colaborador" | E1 |
| `employees.update` | Editar colaborador existente | `employees.edit` | `PATCH /hr/employees/{id}` | `Employees` (edição) | E1 |
| `employees.delete` | Inativar/remover colaborador | `employees.edit` | `DELETE /hr/employees/{id}` | `Employees` (excluir) | E1 |
| `employees.sensitive` | Receber salário, custos, encargos, total, PIX | `employees.view`, `employees.edit` | serializador `include_finance` nos GET de colaborador | Colunas/campos financeiros em `Employees` | E1 |
| `assets.reference` | Usar ativo em seletor | `assets.view`, `assets.edit`* | (a definir) | seletores de ativo | E2+ |
| `assets.list` | Listar ativos **sem** campos monetários | `assets.view` | `GET /assets`, `GET /assets/epis` | `Assets` (grid) | E2+ |
| `assets.read` | Ver detalhe do ativo **sem** monetários | `assets.view` | `GET /assets/{id}` | `AssetDetail` | E2+ |
| `assets.create` | Inserir ativo | `assets.edit` | `POST /assets` | `Assets` (novo) | E2+ |
| `assets.update` | Editar ativo | `assets.edit` | `PATCH /assets/{id}`, assignments | `AssetDetail` | E2+ |
| `assets.delete` | Remover ativo | `assets.edit` | `DELETE /assets/{id}` | `AssetDetail` | E2+ |
| `assets.sensitive` | Receber valores monetários do ativo | `assets.view`, `assets.edit` | serializador `include_finance` nos GET de ativo | valores em `Assets`/`AssetDetail` | E2+ |
| `cost_center.reference` | Escolher Centro de Custo em seletores, sem gestão financeira | `employees.view`, `assets.view`, `projects.view_list`, `company_finance.view`, `vehicles.view` | `GET /cost-centers/reference`, `GET /collaborators/cost-centers` | `CostCenterSelect` (Ativos, cadastros) | **ativo** |
| `vehicles.reference` | Usar veículo em seletor | `vehicles.view`, `vehicles.edit`* | *(a definir)* | seletores de veículo | — |
| `vehicles.list` | Listar veículos **sem** custo mensal | `vehicles.view` | `GET /vehicles`, `GET /vehicles/active` | `Vehicles` (grid) | E-frota |
| `vehicles.read` | Ver detalhe do veículo **sem** custo mensal | `vehicles.view` | *(detalhe)* | `Vehicles` | E-frota |
| `vehicles.create` | Inserir veículo | `vehicles.edit` | `POST /vehicles` | botão "Novo veículo" | **ativo** |
| `vehicles.update` | Editar veículo | `vehicles.edit` | `PATCH /vehicles/{id}` | `Vehicles` (edição) | E-frota |
| `vehicles.delete` | Remover veículo | `vehicles.edit` | `DELETE /vehicles/{id}` | `Vehicles` (excluir) | E-frota |
| `vehicles.sensitive` | Receber `monthly_cost` (custo mensal) | `vehicles.view`, `vehicles.edit` | serializador `include_finance` nos GET de veículo | custo mensal em `Vehicles` | E-frota |

\* Via cadeia de verbos: `create ⇒ reference`.

**Códigos já ativados** (enforçados + na sessão, via `_ACTIVATED_NEW_CODES`): `employees.reference`,
`cost_center.reference`, `employees.create`, `vehicles.create`.

## 4. Compatibilidade e neutralidade (Etapa 0)

- **`ACTIVE_PERMISSION_CODES`**: só os códigos **legados**. `session_permission_names` filtra por esse
  conjunto — os códigos novos não vazam para o frontend. Cada etapa move os códigos do seu módulo
  para "ativo" e repoint os endpoints.
- **Migrations `0092_verb_permission_infra`** (employees/assets/cost_center) e
  **`0093_verb_permissions_vehicles`** (veículos): exclusivamente **aditivas** — criam os códigos novos
  em `permissions` e os adicionam aos perfis de **sistema** (ADMIN/GESTOR/CONSULTA). **Não** alteram
  `user_permissions`, **não** recalculam deltas, **não** tocam perfis customizados.
- **Resolução**: `expand_permissions()` (fecho transitivo de `PERMISSION_IMPLIES`) é usada por
  `app/api/deps.py` e `app/core/session_context.py`. Para códigos legados o resultado é idêntico ao
  anterior (as arestas novas só têm alvos novos). Certificado por `tests/test_permission_verbs.py`
  (golden) e por `scripts/etapa0_neutrality_report.py` (comparação sobre os usuários do banco de dev).

## 5. Rollout

- **E0** — infraestrutura (este documento). Deploy funcionalmente neutro.
- **E1** — Colaboradores: ativa `employees.*`, serializador `include_finance`, `create` separado de `update`.
- **E2** — Ativos: pickers passam a exigir `employees.reference` e `cost_center.reference`.
- **E3** — Projetos: separação dos dados financeiros (`projects.sensitive` / campos de margem/custo).
- **E4** — demais módulos, reaproveitando o padrão.

> Requisito permanente (E1+): todo endpoint novo/alterado tem teste de autorização explícito para
> **permitido / negado / sem sensitive / com sensitive**.
