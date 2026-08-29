import { useMemo } from "react";
import type { EChartsOption } from "echarts";
import { EChart } from "@/components/dashboard/executive/EChart";
import type { Employee } from "@/services/employees";

/**
 * Cards + distribuição por Centro de Custo da relação de colaboradores.
 *
 * Os números refletem os filtros de Competência e Centro de Custo (é a lista que chega em
 * `items`). A Situação NÃO entra aqui de propósito: ela é justamente o que o card de
 * Ativos/Não ativos mostra — filtrar por ela deixaria um dos dois sempre em zero.
 *
 * Exceção: o card de Vínculo (CLT × PJ) e o gráfico por Centro de Custo contam apenas os ATIVOS —
 * são o quadro de pessoal de hoje, e somar desligados distorceria a leitura.
 *
 * Colaborador com alocação em mais de um centro conta em CADA centro no gráfico; por isso a
 * soma das barras pode passar do total de cadastrados.
 */
export function EmployeesOverviewCards({ items }: { items: Employee[] }) {
  const { ativos, inativos, clt, pj, outros, porCentro, somaBarras } = useMemo(() => {
    const contagem = new Map<string, number>();
    let a = 0; // ativos
    let c = 0; // CLT
    let p = 0; // PJ
    let o = 0; // sem vínculo definido
    for (const e of items) {
      // Vínculo e distribuição por centro contam SÓ quem está ativo: desligado não compõe o
      // quadro de pessoal de hoje. O card de Situação é quem mostra os não ativos.
      if (!e.is_active) continue;
      a += 1;
      const tipo = (e.employment_type || "").toUpperCase();
      if (tipo === "CLT") c += 1;
      else if (tipo === "PJ") p += 1;
      else o += 1;
      const centros = e.cost_centers?.length ? e.cost_centers : [e.cost_center || "Sem centro"];
      for (const centro of centros) contagem.set(centro, (contagem.get(centro) ?? 0) + 1);
    }
    const ordenado = [...contagem.entries()].sort((x, y) => y[1] - x[1]);
    return {
      ativos: a,
      inativos: items.length - a,
      clt: c,
      pj: p,
      outros: o,
      porCentro: ordenado,
      somaBarras: ordenado.reduce((s, [, n]) => s + n, 0),
    };
  }, [items]);

  const option = useMemo<EChartsOption>(() => {
    // Barra horizontal: nome de centro é texto longo e não cabe no eixo X.
    const nomes = porCentro.map(([nome]) => nome).reverse();
    const valores = porCentro.map(([, n]) => n).reverse();
    return {
      grid: { left: 8, right: 32, top: 8, bottom: 8, containLabel: true },
      tooltip: { trigger: "item", confine: true },
      xAxis: { type: "value", minInterval: 1, splitLine: { lineStyle: { color: "#eef2f7" } } },
      yAxis: {
        type: "category",
        data: nomes,
        axisTick: { show: false },
        axisLine: { show: false },
        axisLabel: { color: "#475569", fontSize: 12 },
      },
      series: [
        {
          type: "bar",
          data: valores,
          barMaxWidth: 22,
          itemStyle: { color: "#4f46e5", borderRadius: [0, 4, 4, 0] },
          label: { show: true, position: "right", color: "#334155", fontSize: 12 },
        },
      ],
    };
  }, [porCentro]);

  return (
    <div className="grid gap-4 lg:grid-cols-3">
      <div className="grid gap-4 sm:grid-cols-2 lg:col-span-1 lg:grid-cols-1">
        <Card titulo="Cadastrados" valor={items.length} detalhe="no filtro atual" />
        <ParCard
          titulo="Situação"
          esquerda={{ valor: ativos, rotulo: "ativos", cor: "text-emerald-700" }}
          direita={{ valor: inativos, rotulo: "não ativos", cor: "text-slate-500" }}
        />
        <ParCard
          titulo="Vínculo"
          esquerda={{ valor: clt, rotulo: "CLT", cor: "text-indigo-700" }}
          direita={{ valor: pj, rotulo: "PJ", cor: "text-sky-700" }}
          rodape={outros > 0 ? `somente ativos · ${outros} sem vínculo definido` : "somente ativos"}
        />
      </div>

      <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm lg:col-span-2">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <p className="text-sm font-medium text-slate-600">
            Colaboradores por Centro de Custo <span className="font-normal text-slate-400">· somente ativos</span>
          </p>
          {somaBarras > ativos && (
            <p className="text-xs text-slate-400">
              soma {somaBarras} para {ativos} ativos — quem atua em mais de um centro conta em cada um
            </p>
          )}
        </div>
        {porCentro.length === 0 ? (
          <p className="mt-6 text-sm text-slate-500">Nada a exibir com os filtros atuais.</p>
        ) : (
          <EChart option={option} height={Math.max(160, porCentro.length * 34 + 24)} />
        )}
      </div>
    </div>
  );
}

/** Card de duas contagens complementares (ativos/inativos, CLT/PJ). */
function ParCard({
  titulo,
  esquerda,
  direita,
  rodape,
}: {
  titulo: string;
  esquerda: { valor: number; rotulo: string; cor: string };
  direita: { valor: number; rotulo: string; cor: string };
  rodape?: string;
}) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <p className="text-sm font-medium text-slate-600">{titulo}</p>
      <div className="mt-1 flex items-baseline gap-6">
        {[esquerda, direita].map((lado) => (
          <span key={lado.rotulo}>
            <span className={`text-3xl font-semibold tabular-nums ${lado.cor}`}>{lado.valor}</span>
            <span className="ml-1 text-xs text-slate-500">{lado.rotulo}</span>
          </span>
        ))}
      </div>
      {rodape && <p className="mt-1 text-xs text-slate-400">{rodape}</p>}
    </div>
  );
}

function Card({ titulo, valor, detalhe }: { titulo: string; valor: number; detalhe: string }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <p className="text-sm font-medium text-slate-600">{titulo}</p>
      <p className="mt-1 text-3xl font-semibold tabular-nums text-slate-900">{valor}</p>
      <p className="text-xs text-slate-400">{detalhe}</p>
    </div>
  );
}
