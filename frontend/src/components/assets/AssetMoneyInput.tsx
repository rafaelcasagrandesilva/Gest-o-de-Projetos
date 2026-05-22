import {
  formatMoneyFieldBr,
  parseBRLInput,
  sanitizeMoneyTyping,
} from "@/components/assets/assetMoney";

type Props = {
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
  placeholder?: string;
  className?: string;
  inputClassName?: string;
};

export function AssetMoneyInput({
  value,
  onChange,
  disabled,
  placeholder = "Ex.: 500 ou 1.250,90",
  className,
  inputClassName,
}: Props) {
  return (
    <input
      type="text"
      inputMode="decimal"
      autoComplete="off"
      disabled={disabled}
      value={value}
      placeholder={placeholder}
      onChange={(e) => onChange(sanitizeMoneyTyping(e.target.value))}
      onBlur={() => {
        const n = parseBRLInput(value);
        onChange(n > 0 ? formatMoneyFieldBr(n) : "");
      }}
      onPaste={(e) => {
        const pasted = e.clipboardData.getData("text");
        if (!pasted) return;
        e.preventDefault();
        const n = parseBRLInput(pasted);
        onChange(n > 0 ? formatMoneyFieldBr(n) : sanitizeMoneyTyping(pasted));
      }}
      className={
        inputClassName ?? className ?? "mt-1 w-full rounded-lg border border-slate-300 px-3 py-2"
      }
    />
  );
}
