/** Hidden field bots fill in; people never see it (spec §14.16). */
export function Honeypot({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return (
    <div className="absolute -left-[10000px] h-px w-px overflow-hidden" aria-hidden="true">
      <label>
        Website
        <input
          tabIndex={-1}
          autoComplete="off"
          value={value}
          onChange={(e) => {
            onChange(e.target.value);
          }}
        />
      </label>
    </div>
  );
}
