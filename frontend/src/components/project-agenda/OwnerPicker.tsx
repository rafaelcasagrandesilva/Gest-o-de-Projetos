import { useEffect, useRef, useState } from "react";
import type { AgendaUser } from "@/services/projectAgenda";

/**
 * Seletor de RESPONSÁVEIS (um ou mais). Compacto: mostra os nomes escolhidos e abre uma lista com
 * caixas de marcar — cabe numa linha de formulário e dentro de caixas de diálogo.
 */
export function OwnerPicker({
  users,
  value,
  onChange,
  placeholder = "Sem responsável",
}: {
  users: AgendaUser[];
  value: string[];
  onChange: (ids: string[]) => void;
  placeholder?: string;
}) {
  const [aberto, setAberto] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!aberto) return;
    const fechar = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setAberto(false);
    };
    document.addEventListener("mousedown", fechar);
    return () => document.removeEventListener("mousedown", fechar);
  }, [aberto]);

  const nomes = value
    .map((id) => users.find((u) => u.id === id)?.full_name)
    .filter(Boolean)
    .join(", ");

  function alternar(id: string) {
    onChange(value.includes(id) ? value.filter((x) => x !== id) : [...value, id]);
  }

  return (
    <div ref={ref} className="relative mt-1">
      <button
        type="button"
        onClick={() => setAberto((v) => !v)}
        className="flex w-full items-center justify-between gap-2 rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-left text-sm"
      >
        <span className={`truncate ${nomes ? "text-slate-800" : "text-slate-400"}`}>{nomes || placeholder}</span>
        <span className="shrink-0 text-xs text-slate-400">{value.length > 1 ? `${value.length} ▾` : "▾"}</span>
      </button>
      {aberto ? (
        <div className="absolute z-[70] mt-1 max-h-64 w-full min-w-[14rem] overflow-y-auto rounded-lg border border-slate-200 bg-white py-1 shadow-lg">
          {users.map((u) => (
            <label key={u.id} className="flex cursor-pointer items-center gap-2 px-2.5 py-1.5 text-sm text-slate-700 hover:bg-slate-50">
              <input type="checkbox" checked={value.includes(u.id)} onChange={() => alternar(u.id)} />
              {u.full_name}
            </label>
          ))}
          {users.length === 0 ? <p className="px-2.5 py-1.5 text-xs text-slate-500">Nenhum usuário.</p> : null}
        </div>
      ) : null}
    </div>
  );
}
