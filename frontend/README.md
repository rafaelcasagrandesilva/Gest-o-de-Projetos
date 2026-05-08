# SGP — Frontend (React + Vite)

Interface web para consumir a API FastAPI. A URL base é **`VITE_API_BASE`** (veja `.env.example`).

## Requisitos

- Node.js 18+

## Instalação e execução

```bash
cd frontend
npm install
npm run dev
```

Abra **http://localhost:5173** no navegador.

## Build de produção

```bash
npm run build
npm run preview
```

### Deploy (Railway / produção)

A URL da API é resolvida nesta ordem:

1. **`/sgp-runtime-config.js`** (gerado pelo `server.js` em produção) a partir de variáveis do **container do frontend** — **não exige novo build** depois de alterar a env.
2. `VITE_API_BASE` injetada no build (`npm run build`), se existir.
3. Fallback `http://localhost:8000/api/v1` (só desenvolvimento).

**Checklist Railway**

1. **Backend (Python):** anote a URL pública **HTTPS** (ex.: `https://seu-api.up.railway.app`). Em **Variables**, defina `CORS_ORIGINS` = URL do **frontend** (uma origem por linha ou separada por vírgula, conforme o painel), ex.: `https://gest-o-de-projetos-production.up.railway.app`. Defina também `ENV=production`, `DATABASE_URL`, `JWT_SECRET_KEY` (≥ 32 caracteres), etc.
2. **Frontend (Node / `npm start` → `server.js`):** em **Variables**, defina:
   - `VITE_API_BASE` = `https://<URL-DO-BACKEND>/api/v1`  
   (ou use `PUBLIC_API_BASE` com o mesmo valor, se preferir; o servidor aceita os dois nomes.)
3. **Root Directory** do serviço frontend: normalmente `frontend` (se o repositório for a raiz do monorepo).
4. **Build command** (ex.): `npm install && npm run build` e **Start command** (ex.): `npm start` (usa `server.js` na pasta `frontend`).
5. **Redeploy** o frontend após salvar as variáveis (o processo Node precisa reiniciar para ler o `VITE_API_BASE` e o `server.js` passar a expor a URL no script acima).

**Conferir no navegador (F12 → aba Rede):** o primeiro request a `/sgp-runtime-config.js` deve retornar JavaScript com `window.__SGP_API_BASE__="https://.../api/v1"`. O login deve chamar o **mesmo host** do backend, nunca `localhost`.

## Login padrão (após bootstrap do backend)

- Email: `admin@admin.com`
- Senha: `123456`

Certifique-se de que o backend está rodando em `http://localhost:8000` e que o CORS está habilitado (já configurado no `app/main.py`).
