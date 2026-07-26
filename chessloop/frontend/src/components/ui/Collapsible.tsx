import { useState, type ReactNode } from "react";

interface CollapsibleProps {
  title: string;
  defaultOpen?: boolean;
  children: ReactNode;
}

export function Collapsible({ title, defaultOpen = true, children }: CollapsibleProps) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <div className="card">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-2 text-sm font-medium text-ink-300 hover:text-ink-100 transition-colors w-full text-left"
        aria-expanded={open}
      >
        <span className={`inline-block transition-transform duration-150 ${open ? "rotate-90" : ""}`}>
          ▶
        </span>
        {title}
      </button>
      {open && <div className="mt-3">{children}</div>}
    </div>
  );
}
