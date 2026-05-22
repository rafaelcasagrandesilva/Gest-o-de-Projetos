export function AssetSizeBadge({ size }: { size: string | null | undefined }) {
  if (!size?.trim()) return null;
  return (
    <span className="inline-flex rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-700">
      Tam. {size.trim()}
    </span>
  );
}
