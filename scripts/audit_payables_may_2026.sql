-- Auditoria: Contas a Pagar MAIO/2026 (competência de pagamento 2026-05-01)
-- Executar no banco de PRODUÇÃO: psql "$DATABASE_URL" -f scripts/audit_payables_may_2026.sql

\echo '=== 1. Total de snapshots em maio/2026 ==='
SELECT COUNT(*) AS total_rows
FROM payable_snapshots
WHERE month = '2026-05-01';

\echo '=== 2. Por tipo ==='
SELECT type, COUNT(*) AS n,
       SUM(amount_final::numeric) AS soma_final,
       SUM(amount_paid::numeric) AS soma_pago
FROM payable_snapshots
WHERE month = '2026-05-01'
GROUP BY type
ORDER BY type;

\echo '=== 3. Marcador de geração (mês congelado?) ==='
SELECT month, created_at
FROM payable_snapshot_generations
WHERE month = '2026-05-01';

\echo '=== 4. Comparativo 2026 (todos os meses) ==='
SELECT month, COUNT(*) AS n
FROM payable_snapshots
WHERE month >= '2026-01-01' AND month < '2027-01-01'
GROUP BY month
ORDER BY month;

\echo '=== 5. Item TICKET / SUBTERRÂNEO (company_finance) ==='
SELECT id, nome, tipo, cost_center, cost_center_system, cost_center_project_id, updated_at
FROM company_financial_items
WHERE nome ILIKE '%TICKET%' OR nome ILIKE '%SUBTERR%';

\echo '=== 6. Pagamentos mensais do item (se souber o id, ajuste WHERE) ==='
SELECT cfi.nome, cfp.competencia, cfp.valor
FROM company_financial_payments cfp
JOIN company_financial_items cfi ON cfi.id = cfp.item_id
WHERE (cfi.nome ILIKE '%TICKET%' OR cfi.nome ILIKE '%SUBTERR%')
  AND cfp.competencia >= '2026-01-01'
ORDER BY cfi.nome, cfp.competencia;

\echo '=== 7. Snapshots ligados ao item (ref_id) em maio ==='
SELECT ps.id, ps.type, ps.name, ps.cost_center, ps.amount_final, ps.amount_paid, ps.paid, ps.ref_id
FROM payable_snapshots ps
JOIN company_financial_items cfi ON cfi.id = ps.ref_id
WHERE ps.month = '2026-05-01'
  AND (cfi.nome ILIKE '%TICKET%' OR cfi.nome ILIKE '%SUBTERR%');

\echo '=== 8. Linhas MANUAIS em maio (não apagadas por invalidate) ==='
SELECT id, name, cost_center, amount_final, amount_paid
FROM payable_snapshots
WHERE month = '2026-05-01' AND type = 'MANUAL'
ORDER BY name;

\echo '=== 9. Estado “marcador sem linhas” (causa tela vazia + auto-regen antigo) ==='
SELECT g.month, g.created_at,
       (SELECT COUNT(*) FROM payable_snapshots p WHERE p.month = g.month) AS row_count
FROM payable_snapshot_generations g
WHERE g.month = '2026-05-01';

\echo '=== 10. Últimas linhas alteradas em maio (se houver updated_at) ==='
SELECT id, type, name, amount_final, amount_paid, updated_at
FROM payable_snapshots
WHERE month = '2026-05-01'
ORDER BY updated_at DESC NULLS LAST
LIMIT 20;
