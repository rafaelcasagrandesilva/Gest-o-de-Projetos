# Operação em produção e backups

> **Para publicar melhorias no dia a dia**, use o passo a passo em
> [`PUBLICAR_EM_PRODUCAO.md`](PUBLICAR_EM_PRODUCAO.md) — este documento aqui descreve a
> estratégia e as opções; aquele descreve o procedimento.

## Checklist antes de publicar

1. **Variáveis de ambiente** (ver `.env.example`):
   - `ENV=production`
   - `JWT_SECRET_KEY` com **pelo menos 32 caracteres** aleatórios (o backend recusa valores fracos em produção).
   - `CORS_ORIGINS` com o(s) domínio(s) HTTPS do frontend (origens separadas por vírgula).
   - `DATABASE_URL` apontando para o Postgres gerenciado.
   - `AUTH_DEBUG=false`
   - Opcional: `APP_SUPERUSER_EMAILS` para definir quem tem privilégios operacionais de emergência (substitui a lista padrão no código).

2. **Migrations**: o app executa `alembic upgrade head` no startup. Com **vários workers** (vários processos Uvicorn/Gunicorn), pode haver corrida na primeira subida; o ideal é aplicar migrations **uma vez** no deploy (comando de release) e subir os workers depois, ou usar um único worker para o processo que roda migrations.

3. **HTTPS**: use sempre TLS na frente da API (proxy, CDN, Railway, etc.). O middleware `ForwardedProtoMiddleware` já trata `X-Forwarded-Proto`.

4. **Health checks**: use `GET /health` para “vivo” e `GET /health/ready` para “pronto” (inclui ping no banco). Balanceadores devem usar `/health/ready`.

5. **Arquivos**: PDFs de NF ficam em `RECEIVABLE_UPLOAD_DIR`. Faça **backup deste diretório** junto com o banco, ou use storage externo (S3, etc.) em evolução futura.

6. **Pool do banco**: ajuste `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` se tiver muitos usuários simultâneos (valores atuais são conservadores).

---

## Estratégia de backup

### Banco de dados (PostgreSQL)

- **Frequência recomendada**: backup **automático diário** no provedor (RDS, Supabase, Neon, Railway Postgres, etc.) + cópia **mensal** mantida por mais tempo (muitos provedores já oferecem “point in time recovery” — PITR). ⚠️ No nosso caso isso **não está disponível** — o Railway exige o plano Pro; veja "Por que não há backup automático do provedor".
- **Dump lógico próprio**: use o script `scripts/backup_postgres.sh`, que gera um `.sql.gz` e mantém os últimos `RETENTION` arquivos (padrão 12).

Exemplo manual:

```bash
export DATABASE_URL="postgresql://usuario:senha@host:5432/sgp"
./scripts/backup_postgres.sh
```

Cron (1º dia do mês, 03:00):

```cron
0 3 1 * * cd /caminho/do/projeto && DATABASE_URL="..." BACKUP_DIR=/backup/sgp RETENTION=12 ./scripts/backup_postgres.sh >> /var/log/sgp-backup.log 2>&1
```

Requisitos no servidor: cliente PostgreSQL (`pg_dump`).

### Restauração (dump `.sql.gz`)

```bash
gunzip -c var/backups/postgres/sgp_YYYYMMDD_HHMMSS.sql.gz | psql "postgresql://..."
```

Teste **restauração em ambiente de homologação** pelo menos uma vez.

### PDFs / uploads

Copie periodicamente o diretório `RECEIVABLE_UPLOAD_DIR` (ex.: `rsync`, snapshot de disco).

---

## Monitoramento

- Logs da aplicação (stdout/stderr no provedor).
- Alertas no banco: espaço em disco, conexões, CPU.
- Opcional: integrar Sentry ou similar para erros 500 não tratados.

---

# Política de backup — o que fazer e com que frequência

> Escrita em 01/09/2026, com os números reais do sistema em produção. Revisar quando o volume
> mudar de ordem de grandeza.

## O tamanho real do problema

| | Hoje | Implicação |
|---|---|---|
| Banco de dados | **20 MB** (dump comprimido: ~850 KB) | Copiar é questão de segundos |
| Arquivos (volume) | **5,7 MB** — 83 PDFs de NF | Idem |
| Crescimento | ~1.000 registros/mês, acelerando | Um backup completo custa ~7 MB |
| Dado sensível | **151 CPFs**, **68 salários**, dados de processos | LGPD se aplica à cópia |

Guardar **30 backups completos ocupa cerca de 200 MB**. Em outras palavras: no tamanho atual,
não existe razão de custo para fazer backup com pouca frequência ou guardar pouco tempo.

## Os riscos reais, em ordem de probabilidade

1. **Erro humano** — alguém apaga ou altera dados por engano. É de longe a causa mais comum de
   perda em sistemas deste porte. Mitigação: backup diário e o fato de o sistema já não excluir
   fisicamente (exclusão é lógica, com trilha em `audit_logs`).
2. **Backup que existe mas não presta** — arquivo vazio ou corrompido, descoberto na hora do
   desespero. Mitigação: verificação automática (o `backup_completo.sh` aborta se o dump não
   abrir) e teste de restauração periódico.
3. **Perda da máquina** — o notebook quebra, é roubado ou sofre ransomware. Hoje **as duas
   metades do backup vivem só nele**: é o ponto mais frágil da situação atual. Mitigação: cópia
   fora da máquina.
4. **Perda do provedor** — conta suspensa, região fora do ar. Mitigação: a cópia local, que já
   existe.

## A rotina recomendada

| Quando | O que | Como |
|---|---|---|
| **A cada publicação** | Backup completo | `PROD_DB_URL="…" ./scripts/backup_completo.sh` |
| **Toda sexta-feira** | Backup completo | Mesmo comando — protege a semana de trabalho, não só os dias de deploy |
| ~~Todo dia~~ | ~~Backup do banco pelo provedor~~ | **Indisponível no plano atual** — veja abaixo |
| **Todo mês** | Guardar um "selo" | Copie o backup da última sexta do mês para uma pasta `mensais/` |
| **A cada trimestre** | **Teste de restauração** | Restaure o dump no banco local e abra o sistema |

O ponto mais importante da tabela é a linha da sexta-feira. Hoje o backup só acontece quando há
publicação — se uma semana inteira de lançamentos financeiros for feita sem deploy, ela está
desprotegida nesse intervalo.

### Por que não há backup automático do provedor (verificado em 01/09/2026)

A linha riscada acima era uma recomendação que **não se aplica ao nosso projeto**. O Railway
libera backup agendado e PITR (recuperação para um minuto específico) **apenas no plano Pro**;
`bountiful-spirit` está no **Hobby**, e a aba *Backups* do serviço Postgres exibe a mensagem
"Backups and point-in-time recovery (PITR) are only available for customers on the Pro plan",
sem oferecer as opções Daily/Weekly/Monthly. Não é configuração escondida: o recurso está
bloqueado. A CLI também não tem comando de backup — é recurso exclusivo do painel.

Aparecem ali dois itens chamados **"Pre-Security-Patch Backup"**. São cópias que o próprio
Railway tira antes de aplicar patches na infraestrutura dele. São restauráveis, mas acontecem
quando *ele* precisa, não quando *nós* precisamos — não contam como estratégia.

**Consequência prática:** enquanto o plano for Hobby, o `backup_completo.sh` rodado à mão é a
ÚNICA proteção do sistema. A linha da sexta-feira deixa de ser um reforço e passa a ser a
defesa principal. As duas saídas para automatizar, quando fizer sentido:

- **Upgrade para o Pro** — US$ 20/mês por workspace (não por usuário), com o valor vindo como
  crédito de uso. Libera o agendamento e o PITR, roda no servidor e não depende de máquina
  ligada. Cobre só o **banco**: os anexos do volume `/data` continuam por nossa conta.
- **Agendar o `backup_completo.sh` no macOS** — grátis, cobre banco **e** arquivos, e a senha
  fica no Chaveiro em vez de escrita em arquivo. Só roda com o Mac ligado.

Decisão de 01/09/2026: seguir manual por enquanto.

## Onde guardar — a regra das três cópias

Três cópias, em dois lugares diferentes, sendo uma fora do escritório:

1. **Produção** (o dado vivo, no Railway) — não conta como backup, mas é a primeira cópia.
2. **Sua máquina** — `~/sgc-backups`, que é o que o script mantém, com rotação de 30.
3. **Fora da máquina** — uma pasta sincronizada (Google Drive, iCloud, OneDrive) **ou** um HD
   externo atualizado mensalmente.

A terceira é a que falta hoje, e é a que resolve o cenário mais provável de perda total.

## Dado sensível: a cópia fora da máquina precisa de proteção

O backup contém CPF, salários e informações de processos trabalhistas. Numa pasta de nuvem
pessoal, isso é dado pessoal sob a LGPD. Duas formas simples de proteger, em ordem de preferência:

**Criptografar antes de subir** (pede uma senha, que você guarda no gerenciador de senhas):

```bash
gpg -c ~/sgc-backups/backup_producao_ARQUIVO.dump
```

Gera um `.gpg` que só abre com a senha. Suba o `.gpg`, não o original.

**Ou** manter a pasta de nuvem privada, sem compartilhamento com ninguém e com verificação em
duas etapas ativada na conta.

## O que o backup NÃO cobre

- **Variáveis de ambiente e segredos** (`JWT_SECRET_KEY`, `CORS_ORIGINS`, as URLs de banco).
  Sem elas, reconstruir o ambiente do zero é adivinhação. **Guarde uma cópia no gerenciador de
  senhas**, não no repositório.
- **A configuração do Railway** — serviços, volume, domínios. Anotar em um documento simples já
  resolve.

## Teste de restauração — o passo que quase todo mundo pula

Backup nunca restaurado é esperança, não é backup. A cada trimestre:

1. Restaure o dump mais recente no banco local (`sgp_local_test`), que é exatamente o
   procedimento de clone que já existe;
2. Suba o sistema apontando para ele;
3. Abra três telas: um projeto, o Contas a Pagar e um processo do Jurídico;
4. Anote a data do teste.

Se o teste falhar, você descobre num trimestre qualquer — e não no dia em que precisar.

## Quando esta política deve mudar

- **Arquivos passarem de ~1 GB**: mover os anexos para armazenamento de objetos (S3, Cloudflare
  R2) com versionamento. Aí o backup de arquivos deixa de ser um `tar` manual.
- **Banco passar de ~5 GB**: o dump completo deixa de ser instantâneo; avaliar backup incremental
  ou *point-in-time recovery* do provedor.
- **Entrar mais gente lançando dados**: aumentar a frequência de diária para contínua (PITR).
