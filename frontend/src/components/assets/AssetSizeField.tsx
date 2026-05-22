import { SIZE_SUGGESTIONS } from "@/components/assets/assetSize";

type Props = {
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
  className?: string;
};

export function AssetSizeField({ value, onChange, disabled, className }: Props) {
  const listId = "asset-size-suggestions";
  return (
    <label className={className ?? "block text-sm"}>
      <span className="text-slate-600">Tamanho</span>
      <input
        list={listId}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
        placeholder="Ex.: G, 40, M…"
        maxLength={32}
        className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2"
      />
      <datalist id={listId}>
        {SIZE_SUGGESTIONS.map((s) => (
          <option key={s} value={s} />
        ))}
      </datalist>
    </label>
  );
}
