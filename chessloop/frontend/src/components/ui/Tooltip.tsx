import { useState } from "react";

interface TooltipProps {
  text: string;
  children: React.ReactNode;
  disabled?: boolean;
}

export function Tooltip({ text, children, disabled }: TooltipProps) {
  const [isVisible, setIsVisible] = useState(false);

  return (
    <div
      className="relative inline-block"
      onMouseEnter={() => setIsVisible(true)}
      onMouseLeave={() => setIsVisible(false)}
      style={disabled ? { opacity: 0.5 } : undefined}
    >
      {children}

      {isVisible && (
        <div
          className="absolute bottom-full mb-3 bg-ink-800 border border-ink-600 text-ink-200 text-xs rounded px-3 py-2 max-w-sm z-50 pointer-events-none whitespace-normal"
          style={{
            boxShadow: "0 4px 6px rgba(0, 0, 0, 0.3)",
            left: "50%",
            transform: "translateX(60px)",
          }}
        >
          {text}
          {/* Downward-pointing triangle caret */}
          <div
            className="absolute top-full w-0 h-0"
            style={{
              borderLeft: "4px solid transparent",
              borderRight: "4px solid transparent",
              borderTop: "4px solid rgb(30, 30, 40)", // ink-800
              left: "-4px",
            }}
          />
        </div>
      )}
    </div>
  );
}
