import type { Client } from "../lib/api";

export function ClientSelector({
  clients,
  activeId,
  onChange,
}: {
  clients: Client[];
  activeId: string;
  onChange: (id: string) => void;
}) {
  return (
    <div>
      <div className="text-[0.72rem] font-semibold uppercase tracking-wide text-[#475569] mb-1.5">
        Active client
      </div>
      <select
        value={activeId}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-xl border border-line bg-surface px-3 py-2 text-sm text-ink outline-none focus:border-primary cursor-pointer"
      >
        {clients.map((c) => (
          <option key={c.id} value={c.id}>
            {c.label}
          </option>
        ))}
      </select>
    </div>
  );
}
