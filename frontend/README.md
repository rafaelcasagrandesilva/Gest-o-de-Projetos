# SGP — Frontend (React + Vite)

Interface web para consumir a API FastAPI em `http://localhost:8000/api/v1`.

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

## Login padrão (após bootstrap do backend)

- Email: `admin@admin.com`
- Senha: `123456`

Certifique-se de que o backend está rodando em `http://localhost:8000` e que o CORS está habilitado (já configurado no `app/main.py`).
