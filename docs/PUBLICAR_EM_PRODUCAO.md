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

Três coisas, uma única vez. Depois disso, todas as publicações seguem direto para a Parte 1.

**1. Entrar na sua conta do Railway** — abre o navegador para você autenticar:

```bash
railway login
```

**2. Criar uma chave de acesso** — é o que permite copiar os arquivos do servidor. Se você já
tiver uma, ele avisa e não sobrescreve:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519 -N ""
```

**3. Conectar esta pasta ao projeto** — responda às perguntas com as setas e Enter:

```bash
railway link
```

| Pergunta | Resposta |
|---|---|
| Workspace | a sua conta |
| Project | **bountiful-spirit** |
| Environment | **production** |
| Service | **celebrated-nature** |

Na primeira vez que rodar o backup dos arquivos, ainda aparecerão duas perguntas: autorizar a
chave (**Y**) e confiar no servidor `ssh.railway.com` (digite **`yes`**, a palavra inteira). Não
voltam a aparecer.

---

# PARTE 1 · Backup — a sua rede de segurança

## 1.1 · Um comando só

Cole a URL pública do banco no lugar indicado e rode:

```bash
PROD_DB_URL="COLE_AQUI_A_URL_PUBLICA" ./scripts/backup_completo.sh
```

Ele copia **as duas metades** do sistema — o banco e os arquivos —, confere se ficaram íntegras e
mantém os 30 backups mais recentes em `~/sgc-backups`.

**Onde pegar a URL:** no Railway, serviço **Postgres** → aba **Variables** → copie
**`DATABASE_PUBLIC_URL`** (a pública, não a `DATABASE_URL`). Se ela começar com
`postgresql+asyncpg://`, tudo bem: o script converte sozinho.

**O que você deve ver no fim:**

```
✅ BACKUP COMPLETO — 01/09/2026 07:20
   Banco:    backup_producao_20260901_072015.dump
   Arquivos: arquivos_20260901_072015.tar.gz
```

**Se aparecer `❌ BACKUP INCOMPLETO`, pare.** A mensagem diz o motivo, e o script já verificou
que o arquivo gerado não presta — publicar sem rede de segurança é o risco que estamos evitando.
Nesse caso, me chame.

> **Por que as duas metades:** o banco guarda os *registros*; os PDFs e documentos ficam num
> disco à parte, o "volume". Restaurar só o banco devolveria os cadastros com os arquivos
> aparecendo como "não encontrado".

> **Cuidado:** a URL contém a **senha do banco de produção**. Não cole em e-mail, chat, ticket ou
> documento compartilhado. Se acontecer sem querer, troque a senha no Railway e faça um redeploy.

## 1.2 · Anote a versão que está no ar hoje

Isto é o que permite voltar atrás depois:

```bash
git ls-remote origin main | cut -c1-7
```

Ele imprime sete letras e números (exemplo: `21f4c07`). **Anote.** É o "endereço" da versão que
está funcionando agora.

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
pg_restore --dbname="COLE_AQUI_A_URL_PUBLICA" --clean --if-exists --no-owner ~/sgc-backups/backup_producao_ARQUIVO.dump
```

## 4.3 · Arquivos (PDFs, anexos) sumiram

Primeiro descubra o tamanho do problema: o próprio sistema tem o diagnóstico em
**Configurações → Arquivos ausentes no servidor**, que lista o que existe no cadastro mas não
está no disco.

Para repor a partir do seu backup, me chame — a restauração devolve os arquivos ao servidor e
convém fazer junto, conferindo caso a caso. O seu `.tar.gz` tem tudo o que é preciso; o que não
existe é um botão de "restaurar volume" no painel do Railway.

---

# Resumo — a sequência, sem explicações

Quando estiver acostumado, é isto:

```bash
PROD_DB_URL="COLE_AQUI_A_URL_PUBLICA" ./scripts/backup_completo.sh
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

Depois: acompanhar o deploy no Railway e testar o sistema.

---

# Perguntas frequentes

**Preciso fazer backup toda vez?**
Sim — é um comando e menos de dois minutos. E não só ao publicar: faça também **toda sexta-feira**,
para proteger a semana de trabalho. A política completa está em
[`operacao-e-backups.md`](operacao-e-backups.md).

**Posso publicar sem testar antes?**
Pode, mas não deve. O teste é o que separa "melhoria" de "problema descoberto pela equipe".

**E se eu commitar algo errado sem querer?**
Enquanto não fizer o `git push`, nada saiu da sua máquina. Depois do push, use o passo 4.1.

**Quanto tempo o backup fica guardado?**
Os arquivos ficam na sua pasta `~/sgc-backups` até você apagar. Vale manter pelo menos os três
últimos e apagar os mais antigos de vez em quando.

**O sistema fica fora do ar durante a publicação?**
Por alguns segundos, na troca de versão. Evite publicar em horário de pico.

---

# Apêndice · Backup na mão (só se o script falhar)

O `backup_completo.sh` faz estes dois passos. Se precisar executá-los separadamente:

**Banco:**

```bash
mkdir -p ~/sgc-backups && pg_dump --dbname="COLE_AQUI_A_URL_PUBLICA" --format=custom --file="$HOME/sgc-backups/backup_producao_$(date +%Y%m%d_%H%M%S).dump"
```

**Arquivos** (a mensagem `Removing leading '/' from member names` é normal):

```bash
railway ssh --service celebrated-nature "tar czf - /data" > ~/sgc-backups/arquivos_$(date +%Y%m%d_%H%M%S).tar.gz
```

**Conferência** — obrigatória, porque arquivo corrompido não dá erro na hora:

```bash
tar tzf "$(ls -t ~/sgc-backups/arquivos_*.tar.gz | head -1)" | head -5
```

**Limpeza** dos arquivos vazios que tentativas falhas deixam para trás:

```bash
find ~/sgc-backups -name "arquivos_*.tar.gz" -size -10k -delete
```
