/** Formatação e cores do ROI Operacional — fonte única para toda a tela de Indicadores. */

export type RoiToneKey = "verde" | "amarelo" | "vermelho" | "cinza";

export interface RoiTone {
  key: RoiToneKey;
  /** classes para card/borda */
  card: string;
  /** classe de cor de texto */
  text: string;
  /** badge/pílula */
  badge: string;
  /** ponto/indicador (bg) */
  dot: string;
}

/** >20% verde · 0–20% amarelo · <0 vermelho · null cinza. */
export function roiTone(roi: number | null): RoiTone {
  if (roi === null) {
    return {
      key: "cinza",
      card: "border-slate-200",
      text: "text-slate-400",
      badge: "bg-slate-100 text-slate-500",
      dot: "bg-slate-300",
    };
  }
  if (roi > 0.2) {
    return {
      key: "verde",
      card: "border-emerald-200",
      text: "text-emerald-600",
      badge: "bg-emerald-100 text-emerald-700",
      dot: "bg-emerald-500",
    };
  }
  if (roi >= 0) {
    return {
      key: "amarelo",
      card: "border-amber-200",
      text: "text-amber-600",
      badge: "bg-amber-100 text-amber-700",
      dot: "bg-amber-500",
    };
  }
  return {
    key: "vermelho",
    card: "border-rose-200",
    text: "text-rose-600",
    badge: "bg-rose-100 text-rose-700",
    dot: "bg-rose-500",
  };
}

/** Ex.: 0,327 → "32,7%". null → "—". */
export function formatRoiPct(roiPct: number | null): string {
  if (roiPct === null || !Number.isFinite(roiPct)) return "—";
  return `${roiPct.toFixed(1).replace(".", ",")}%`;
}

/** "YYYY-MM" do mês atual (input month). */
export function currentMonth(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
}

/** "YYYY-MM" → "YYYY-MM-01" (competência que o backend espera). */
export function monthToCompetencia(month: string): string {
  return `${month}-01`;
}

/** Date → "YYYY-MM". */
function dateToMonth(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

/** "YYYY-MM" menos n meses → "YYYY-MM". */
export function monthMinus(month: string, n: number): string {
  const [y, m] = month.split("-").map(Number);
  const d = new Date(y, (m - 1) - n, 1);
  return dateToMonth(d);
}

/** Início do ano da competência informada (mês "YYYY-MM"). */
export function startOfYear(month: string): string {
  const [y] = month.split("-").map(Number);
  return `${y}-01`;
}

/** "YYYY-MM" → "mm/aaaa" para eixos/rótulos. */
export function monthLabel(competencia: string): string {
  // aceita "YYYY-MM" ou "YYYY-MM-01"
  const [y, m] = competencia.split("-");
  return `${m}/${y}`;
}
