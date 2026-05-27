const MONTH_ABBR = ["JAN", "FEV", "MAR", "ABR", "MAI", "JUN", "JUL", "AGO", "SET", "OUT", "NOV", "DEZ"] as const;

/** Ex.: `2026-02-01` → `FEV/2026` */
export function payableCompetenceLabel(monthIso: string): string {
  const ym = monthIso.slice(0, 7);
  const [y, m] = ym.split("-").map(Number);
  if (!y || !m || m < 1 || m > 12) return ym;
  return `${MONTH_ABBR[m - 1]}/${y}`;
}

/** Ex.: `2026-03-27` → `MAR/2026` (mês do fluxo de caixa) */
export function payableCashFlowLabelFromDate(isoDate: string): string {
  if (!isoDate || isoDate.length < 7) return "—";
  return payableCompetenceLabel(`${isoDate.slice(0, 7)}-01`);
}

export function todayIsoLocal(): string {
  const t = new Date();
  const y = t.getFullYear();
  const m = String(t.getMonth() + 1).padStart(2, "0");
  const d = String(t.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}
