# Ponto de Restauração — Otimização de Densidade Visual

> Snapshot completo do sistema **antes** da Fase 2 (otimização global de layout/densidade).
> As mudanças após este ponto são **exclusivamente visuais** — nenhuma regra de negócio,
> endpoint, banco, permissão, cálculo ou KPI foi alterado.

## Identificação

- **Data/hora:** 2026-06-11 (gerado na criação do restore point)
- **Branch de trabalho:** `layout-density-optimization`
- **Commit do restore point (snapshot):** `59c2f7dd0fde2d32444b907e502c1e72851bc704`
- **Tag de restauração:** `pre-layout-density-optimization`
- **Commit anterior em `main`:** `d0b5e5de9f599886ceb76efe79a1dd6fb0721d5c`

## Como restaurar (rollback)

### Opção A — voltar para o snapshot pré-layout (recomendado)
Restaura exatamente o estado capturado antes das mudanças visuais, preservando todo o
trabalho funcional da sessão:

```bash
cd Gest-o-de-Projetos
git checkout layout-density-optimization
git reset --hard pre-layout-density-optimization
```

ou, de forma equivalente, via tag:

```bash
git checkout tags/pre-layout-density-optimization
```

### Opção B — descartar TUDO e voltar para a main original
Atenção: descarta também todo o trabalho funcional desta sessão (módulo Indicadores,
Extrato Analítico, etc.), retornando ao último commit da `main`:

```bash
git checkout main
git reset --hard d0b5e5de9f599886ceb76efe79a1dd6fb0721d5c
```

### Verificação pós-rollback
```bash
git status            # working tree deve ficar limpo
git rev-parse HEAD    # deve bater com o hash escolhido
```

## Integridade validada na criação do restore point

- **Backend (testes):** registrado no relatório da Fase 1.
- **Frontend (typecheck + build):** registrado no relatório da Fase 1.
