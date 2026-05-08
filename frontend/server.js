/**
 * Servidor estático para produção (Railway, etc.).
 * - PORT: obrigatório no Railway (string numérica no env).
 * - Host 0.0.0.0: obrigatório para o healthcheck/proxy do Railway alcançar o processo.
 * - Fallback SPA via middleware final (compatível Express 4/5; evita wildcard problemático em Express 5).
 */
import express from "express";
import path from "path";
import { fileURLToPath } from "url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const distDir = path.join(__dirname, "dist");
const app = express();

app.disable("x-powered-by");
app.set("trust proxy", 1);

const port = Number.parseInt(String(process.env.PORT ?? "3000"), 10);
if (Number.isNaN(port) || port < 1) {
  console.error("[frontend] PORT inválido:", process.env.PORT);
  process.exit(1);
}

const host = "0.0.0.0";

app.get("/healthz", (_req, res) => {
  res.status(200).type("text/plain").send("ok");
});

/**
 * Injeta URL da API em runtime (Railway): não depende só do `vite build` embutindo VITE_*.
 * Prioriza VITE_API_BASE; aceita PUBLIC_API_BASE como alias no painel.
 * Registrar ANTES do express.static para prevalecer sobre arquivo em `dist/`.
 */
app.get("/sgp-runtime-config.js", (_req, res) => {
  const base = String(process.env.VITE_API_BASE || process.env.PUBLIC_API_BASE || "").trim();
  res.type("application/javascript");
  res.setHeader("Cache-Control", "no-store");
  res.send(`window.__SGP_API_BASE__=${JSON.stringify(base)};`);
});

app.use(express.static(distDir));

app.use((req, res, next) => {
  if (req.method !== "GET" && req.method !== "HEAD") {
    res.status(405).end();
    return;
  }
  res.sendFile(path.join(distDir, "index.html"), (err) => {
    if (err) next(err);
  });
});

const server = app.listen(port, host, () => {
  console.log(`[frontend] listening on http://${host}:${port} (dist=${distDir})`);
});

server.on("error", (err) => {
  console.error("[frontend] listen error:", err);
  process.exit(1);
});
