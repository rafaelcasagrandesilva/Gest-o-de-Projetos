import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { searchCollaborators, type CollaboratorSearchItem } from "@/services/employees";
import { isAxiosError } from "axios";

function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = window.setTimeout(() => setDebounced(value), delayMs);
    return () => window.clearTimeout(t);
  }, [value, delayMs]);
  return debounced;
}

type Props = {
  label: string;
  value: string;
  onChange: (id: string) => void;
  /** Chamado ao escolher um item da lista (id + nome). */
  onPick?: (item: CollaboratorSearchItem) => void;
  placeholder?: string;
  disabled?: boolean;
  /** nome já resolvido (para mostrar quando value estiver preenchido) */
  selectedName?: string | null;
};

export function CollaboratorSelect({
  label,
  value,
  onChange,
  onPick,
  placeholder = "Buscar colaborador…",
  disabled,
  selectedName,
}: Props) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [items, setItems] = useState<CollaboratorSearchItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const debouncedQuery = useDebouncedValue(query, 300);
  const boxRef = useRef<HTMLDivElement | null>(null);

  const displayValue = useMemo(() => {
    if (!value) return "";
    return selectedName ?? value.slice(0, 8) + "…";
  }, [value, selectedName]);

  const load = useCallback(async () => {
    const q = debouncedQuery.trim();
    setError(null);
    if (!q) {
      setItems([]);
      return;
    }
    setLoading(true);
    try {
      const res = await searchCollaborators({ q, limit: 20 });
      setItems(res);
    } catch (e) {
      if (isAxiosError(e)) setError(String(e.response?.data?.detail ?? e.message));
      else setError("Erro ao buscar colaboradores.");
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, [debouncedQuery]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    function onDocClick(ev: MouseEvent) {
      const el = boxRef.current;
      if (!el) return;
      if (ev.target instanceof Node && el.contains(ev.target)) return;
      setOpen(false);
    }
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, []);

  return (
    <div ref={boxRef} className="relative">
      <label className="mb-1 block text-sm text-slate-600">{label}</label>
      <div className="flex gap-2">
        <input
          value={open ? query : displayValue}
          onChange={(e) => {
            setQuery(e.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          placeholder={placeholder}
          disabled={disabled}
          className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
        />
        {value && !disabled ? (
          <button
            type="button"
            onClick={() => {
              onChange("");
              setQuery("");
              setItems([]);
            }}
            className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-medium text-slate-700 hover:bg-slate-50"
          >
            Limpar
          </button>
        ) : null}
      </div>

      {open ? (
        <div className="absolute z-20 mt-1 w-full rounded-lg border border-slate-200 bg-white shadow-lg">
          {loading ? (
            <div className="px-3 py-2 text-sm text-slate-500">Buscando…</div>
          ) : error ? (
            <div className="px-3 py-2 text-sm text-red-700">{error}</div>
          ) : items.length === 0 ? (
            <div className="px-3 py-2 text-sm text-slate-500">Nenhum resultado.</div>
          ) : (
            <ul className="max-h-[260px] overflow-auto py-1 text-sm">
              {items.map((it) => (
                <li key={it.id}>
                  <button
                    type="button"
                    onClick={() => {
                      onChange(it.id);
                      onPick?.(it);
                      setOpen(false);
                      setQuery("");
                      setItems([]);
                    }}
                    className="w-full px-3 py-2 text-left hover:bg-slate-50"
                  >
                    <span className="font-medium text-slate-900">{it.name}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      ) : null}
    </div>
  );
}

