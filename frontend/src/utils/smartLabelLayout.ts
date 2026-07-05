/**
 * Layout inteligente de rótulos para gráficos ECharts (estilo Power BI/Tableau).
 *
 * Substitui o comportamento baseado apenas em `hideOverlap`. É usado como callback
 * de `series.labelLayout` — o ECharts o invoca para CADA rótulo visível a cada
 * render (zoom, resize, troca de legenda, etc.), então o posicionamento é sempre
 * recalculado do zero, aproveitando o espaço que séries ocultas liberam.
 *
 * Heurística: para cada rótulo (badge + valor tratados como um único bloco) tenta
 * várias posições em ordem de prioridade — acima, abaixo, direita, esquerda e as
 * quatro diagonais — e escolhe a primeira que não colide com rótulos já colocados.
 *
 * - Modo normal: uma "órbita" (offset pequeno); se nada couber, deixa o ECharts
 *   ocultar (prioriza limpeza visual).
 * - Modo expandido: várias órbitas cada vez mais distantes, deslocamentos maiores
 *   e linha-guia (leader line); prefere deslocar a ocultar (prioriza informação).
 */

export interface LabelRect {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface LabelLayoutParams {
  seriesIndex: number;
  dataIndex: number;
  rect: LabelRect;
  labelRect: LabelRect;
}

export interface LabelLayoutResult {
  x?: number;
  y?: number;
  align?: "left" | "center" | "right";
  verticalAlign?: "top" | "middle" | "bottom";
  hideOverlap?: boolean;
  moveOverlap?: boolean;
  labelLinePoints?: number[][];
}

/** Direções em ordem de prioridade (item 3 do refinamento). */
const DIRECTIONS = ["top", "bottom", "right", "left", "tr", "br", "tl", "bl"] as const;
type Direction = (typeof DIRECTIONS)[number];

interface Candidate {
  x: number;
  y: number;
  displaced: boolean;
}

function intersects(a: LabelRect, b: LabelRect, pad = 2): boolean {
  return !(
    a.x + a.width + pad <= b.x ||
    b.x + b.width + pad <= a.x ||
    a.y + a.height + pad <= b.y ||
    b.y + b.height + pad <= a.y
  );
}

export interface SmartLabelLayoutOptions {
  /** modo expandido = mais agressivo (mais órbitas, leader lines, nunca oculta) */
  expanded: boolean;
}

export function createSmartLabelLayout(
  { expanded }: SmartLabelLayoutOptions,
): (params: LabelLayoutParams) => LabelLayoutResult {
  // Acumulador de retângulos já posicionados NA passada atual de layout.
  let placed: LabelRect[] = [];
  const seen = new Set<string>();

  // Órbitas (multiplicadores de distância). Expandido tenta muito mais longe.
  const rings = expanded ? [1, 1.7, 2.5, 3.4] : [1];
  const baseGap = expanded ? 16 : 10;

  function candidatesFor(px: number, py: number, lw: number, lh: number): Candidate[] {
    const out: Candidate[] = [];
    for (let ri = 0; ri < rings.length; ri++) {
      const m = rings[ri];
      const gx = (baseGap + lw / 2) * m;
      const gy = (baseGap + lh / 2) * m;
      const dgx = gx * 0.8;
      const dgy = gy * 0.8;
      const byDir: Record<Direction, Candidate> = {
        top: { x: px, y: py - gy, displaced: ri > 0 },
        bottom: { x: px, y: py + gy, displaced: true },
        right: { x: px + gx, y: py, displaced: true },
        left: { x: px - gx, y: py, displaced: true },
        tr: { x: px + dgx, y: py - dgy, displaced: true },
        br: { x: px + dgx, y: py + dgy, displaced: true },
        tl: { x: px - dgx, y: py - dgy, displaced: true },
        bl: { x: px - dgx, y: py + dgy, displaced: true },
      };
      for (const d of DIRECTIONS) out.push(byDir[d]);
    }
    return out;
  }

  return (params: LabelLayoutParams): LabelLayoutResult => {
    const key = `${params.seriesIndex}:${params.dataIndex}`;
    // Detecta o início de uma nova passada de layout: se a chave já foi vista,
    // o ECharts recomeçou o ciclo — zera o acumulador (recálculo do zero).
    if (seen.has(key) || placed.length > 512) {
      seen.clear();
      placed = [];
    }
    seen.add(key);

    const anchor = params.rect ?? params.labelRect;
    const px = anchor.x + anchor.width / 2;
    const py = anchor.y + anchor.height / 2;
    const lw = params.labelRect.width;
    const lh = params.labelRect.height;

    const candidates = candidatesFor(px, py, lw, lh);

    for (const c of candidates) {
      const rect: LabelRect = { x: c.x - lw / 2, y: c.y - lh / 2, width: lw, height: lh };
      if (!placed.some((p) => intersects(rect, p))) {
        placed.push(rect);
        const result: LabelLayoutResult = {
          x: c.x,
          y: c.y,
          align: "center",
          verticalAlign: "middle",
          hideOverlap: false,
          moveOverlap: false,
        };
        if (expanded && c.displaced) result.labelLinePoints = [[px, py], [c.x, c.y]];
        return result;
      }
    }

    // Nenhuma posição livre.
    if (expanded) {
      // Prefere deslocar (posição mais distante) com leader line a ocultar.
      const c = candidates[candidates.length - 1];
      placed.push({ x: c.x - lw / 2, y: c.y - lh / 2, width: lw, height: lh });
      return {
        x: c.x,
        y: c.y,
        align: "center",
        verticalAlign: "middle",
        hideOverlap: false,
        labelLinePoints: [[px, py], [c.x, c.y]],
      };
    }
    // Modo normal: como último recurso, deixa o ECharts ocultar este rótulo.
    return { hideOverlap: true };
  };
}
