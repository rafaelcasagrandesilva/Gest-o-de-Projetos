# Publicar melhorias em produção — passo a passo

Guia para executar **toda vez** que quiser levar melhorias já testadas para o ambiente que a
equipe usa. Escrito para ser seguido sem conhecimento técnico prévio: cada comando vem com a
explicação do que ele faz e do que você deve ver quando der certo.

**Tempo estimado:** 15 minutos, sendo 10 de espera.

---

## Antes de tudo: os três lugares

| Lugar | O que é | Como o código chega lá |
|---|---|---|
| **Sua máquina** | Onde as melhorias são feitas e testadas | — |
| **GitHub** | O "cofre" com o histórico de todas as versões | Você envia com `git push` |
| **Railway** | O ambiente de produção, que a equipe acessa | Sozinho, assim que o GitHub recebe |

O ponto importante: **quem dispara a publicação é o `git push`**. Enquanto você não fizer o push,
nada muda para a equipe — pode testar à vontade.

---

## Preparação (só na primeira vez)

Conectar o Railway à sua máquina, para conseguir fazer o backup dos arquivos:

```bash
railway login
```

Abre o navegador para você entrar com a sua conta. Feito uma vez, vale por muito tempo.

---

# PARTE 1 · Backup — a sua rede de segurança

O sistema tem **duas coisas** que precisam de cópia, e uma não substitui a outra:

- **O banco de dados** — processos, notas fiscais, colaboradores, lançamentos. Todo o dado.
- **Os arquivos** — PDFs de NF, anexos de ativos e documentos de projeto. Eles não estão no
  banco: ficam num disco à parte (o "volume").

Restaurar só o banco traria os *registros* dos documentos, mas os arquivos apareceriam como
"não encontrado". Por isso os dois passos.

## 1.1 · Backup do banco

Primeiro, pegue o endereço do banco de produção: no Railway, abra o serviço **Postgres** → aba
**Variables** → copie o valor de `DATABASE_URL`.

Depois rode, colando o endereço no lugar indicado:

```bash
mkdir -p ~/sgc-backups && pg_dump --dbname="COLE_AQUI_A_DATABASE_URL" --format=custom --file="$HOME/sgc-backups/backup_producao_$(date +%Y%m%d_%H%M%S).dump"
```

**O que ele faz:** copia o banco inteiro de produção para um arquivo na sua pasta pessoal.
Não altera nada em produção — só lê.

**Como saber que deu certo:** o comando termina sem mensagem de erro e o arquivo aparece:

```bash
ls -lh ~/sgc-backups/ | tail -3
```

Você deve ver um arquivo `backup_producao_<data>_<hora>.dump` com algumas centenas de KB.
Um arquivo com 0 bytes significa que algo falhou — não prossiga.

> **Cuidado:** a `DATABASE_URL` é a senha do banco. Não cole em e-mail, chat ou documento
> compartilhado.

## 1.2 · Backup dos arquivos (o volume)

**Caminho mais simples — pelo painel:** no Railway, clique no volume ligado ao serviço
`celebrated-nature` → aba **Backups** → criar backup. É o mesmo recurso que o volume do Postgres
oferece.

**Alternativa pela linha de comando**, se preferir ter o arquivo na sua máquina:

```bash
railway ssh --service celebrated-nature "tar czf - /data" > ~/sgc-backups/arquivos_$(date +%Y%m%d_%H%M%S).tar.gz
```

**Como saber que deu certo:** o arquivo `.tar.gz` tem tamanho compatível com os anexos (vários
MB, não alguns KB).

## 1.3 · Anote a versão que está no ar hoje

Isto é o que permite voltar atrás depois:

```bash
git ls-remote origin main | cut -c1-7
```

Ele imprime sete letras e números (exemplo: `21f4c07`). **Anote.** É o "endereço" da versão que
está funcionando agora.

---

# PARTE 2 · Publicar

## 2.1 · Ver o que vai subir

```bash
git status --short
```

Ele lista os arquivos alterados. Leia a lista com atenção: **tudo o que estiver aí vai para
produção**. Se aparecer algo que você não reconhece ou que ainda não testou, pare e me pergunte
antes de continuar.

## 2.2 · Guardar as alterações

```bash
git add -A && git commit -m "descreva aqui, em uma frase, o que está subindo"
```

**O que ele faz:** registra as alterações no histórico da sua máquina, com um nome. Ainda **não**
publica nada.

## 2.3 · Publicar

```bash
git push origin main
```

**O que ele faz:** envia para o GitHub — e é isso que faz o Railway começar a publicar
automaticamente. A partir daqui, a mudança está a caminho da equipe.

**Como saber que deu certo:** o comando termina com algo como
`main -> main`. Se disser `Everything up-to-date`, é porque não havia nada novo para enviar.

---

# PARTE 3 · Conferir (não pule)

## 3.1 · Acompanhe a publicação

No Railway, abra o serviço `celebrated-nature` → aba **Deployments**. Aguarde o status virar
**Success** (costuma levar de 2 a 5 minutos).

## 3.2 · Veja se o sistema respondeu

Nos **logs** do mesmo serviço, procure por estas linhas no início:

- `alembic upgrade head` sem mensagem de erro — quer dizer que o banco foi atualizado
- linhas começando com `Storage:` — devem mostrar caminhos que começam com `/data`

Se aparecer um aviso dizendo que algum diretório é relativo, me chame: significa que os arquivos
enviados hoje se perderiam no próximo deploy.

## 3.3 · Teste no sistema

Abra o sistema como a equipe usa e confira **as melhorias que você aprovou**. Além delas, um
teste rápido que vale sempre:

- abrir um projeto e **baixar um documento** (garante que os arquivos continuam acessíveis)
- abrir uma tela do Financeiro (garante que o banco atualizou sem quebrar nada)

---

# PARTE 4 · Se algo der errado

Mantenha a calma: o passo 1.3 existe justamente para isto.

## 4.1 · O sistema abriu mas está com problema

Desfaz a última publicação e volta ao que funcionava:

```bash
git revert --no-edit HEAD && git push origin main
```

Em poucos minutos o Railway republica a versão anterior. **Esta é a saída para 9 de cada 10
problemas** — use sem medo, ela não apaga nada.

## 4.2 · O problema é no banco de dados

Só use se o dado ficou errado ou sumiu — restaurar o banco desfaz **tudo o que a equipe fez
desde o backup**. Antes de rodar, avise quem estiver usando o sistema. Se tiver qualquer dúvida,
me chame antes:

```bash
pg_restore --dbname="COLE_AQUI_A_DATABASE_URL" --clean --if-exists --no-owner ~/sgc-backups/backup_producao_ARQUIVO.dump
```

## 4.3 · Arquivos (PDFs, anexos) sumiram

Restaure o backup do volume pelo painel do Railway (aba **Backups** do volume). Para descobrir
exatamente o que está faltando, o próprio sistema tem o diagnóstico:
**Configurações → Arquivos ausentes no servidor**.

---

# Resumo — a sequência, sem explicações

Quando estiver acostumado, é isto:

```bash
mkdir -p ~/sgc-backups && pg_dump --dbname="URL_DO_BANCO" --format=custom --file="$HOME/sgc-backups/backup_producao_$(date +%Y%m%d_%H%M%S).dump"
```

```bash
git ls-remote origin main | cut -c1-7
```

```bash
git status --short
```

```bash
git add -A && git commit -m "o que está subindo"
```

```bash
git push origin main
```

Depois: backup do volume pelo painel, acompanhar o deploy e testar.

---

# Perguntas frequentes

**Preciso fazer backup toda vez?**
Do banco, sim — é rápido e é o que permite voltar atrás. Do volume, sempre que a publicação mexer
em anexos ou documentos; nas demais, o backup do painel do Railway já cobre.

**Posso publicar sem testar antes?**
Pode, mas não deve. O teste é o que separa "melhoria" de "problema descoberto pela equipe".

**E se eu commitar algo errado sem querer?**
Enquanto não fizer o `git push`, nada saiu da sua máquina. Depois do push, use o passo 4.1.

**Quanto tempo o backup fica guardado?**
Os arquivos ficam na sua pasta `~/sgc-backups` até você apagar. Vale manter pelo menos os três
últimos e apagar os mais antigos de vez em quando.

**O sistema fica fora do ar durante a publicação?**
Por alguns segundos, na troca de versão. Evite publicar em horário de pico.
