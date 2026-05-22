import { EXPIRATION_SHORT_LABELS } from "@/components/assets/assetLabels";
import type { ExpirationAlertLevel } from "@/services/assets";

const STYLES: Record<ExpirationAlertLevel, string> = {
  NORMAL: "bg-slate-100 text-slate-700",
  YELLOW: "bg-yellow-100 text-yellow-900",
  ORANGE: "bg-orange-100 text-orange-900",
  TOMORROW: "bg-orange-100 text-orange-900",
  RED: "bg-red-100 text-red-900",
};

type Props = {
  /** Exibir somente quando o ativo possui ensaio/inspeção com validade configurada. */
  show?: boolean;
  level: ExpirationAlertLevel | null | undefined;
  date?: string | null;
  compact?: boolean;
};

export function AssetExpirationBadge({ show = true, level, date, compact }: Props) {
  if (!show || !level) return null;
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${STYLES[level]}`}>
      {EXPIRATION_SHORT_LABELS[level]}
      {!compact && date ? <span className="opacity-80">({date})</span> : null}
    </span>
  );
}
