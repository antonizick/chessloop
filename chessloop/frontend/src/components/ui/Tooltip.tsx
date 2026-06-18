import { useRef, useState } from "react";

interface TooltipProps {
  text: string;
  children: React.ReactNode;
  disabled?: boolean;
  wide?: boolean;
}

export function Tooltip({ text, children, disabled, wide }: TooltipProps) {
  const [isVisible, setIsVisible] = useState(false);
  const triggerRef = useRef<HTMLDivElement>(null);
  const [position, setPosition] = useState({ top: 0, left: 0 });

  const handleMouseEnter = () => {
    if (triggerRef.current) {
      const rect = triggerRef.current.getBoundingClientRect();
      setPosition({
        top: rect.top - 8,
        left: rect.right + 12,
      });
    }
    setIsVisible(true);
  };

  return (
    <div
      ref={triggerRef}
      className="inline-block"
      onMouseEnter={handleMouseEnter}
      onMouseLeave={() => setIsVisible(false)}
      style={disabled ? { opacity: 0.5 } : undefined}
    >
      {children}

      {isVisible && (
        <div
          className={`fixed bg-ink-800 border border-ink-600 text-ink-200 text-xs rounded px-3 py-2 ${wide ? "max-w-lg" : "max-w-sm"} z-50 pointer-events-none whitespace-normal`}
          style={{
            boxShadow: "0 4px 6px rgba(0, 0, 0, 0.3)",
            top: `${position.top}px`,
            left: `${position.left}px`,
            transform: "translateY(-100%)",
          }}
        >
          {text}
          {/* Downward-pointing triangle caret */}
          <div
            className="absolute w-0 h-0"
            style={{
              borderLeft: "4px solid transparent",
              borderRight: "4px solid transparent",
              borderTop: "4px solid rgb(30, 30, 40)",
              left: "12px",
              bottom: "-4px",
            }}
          />
        </div>
      )}
    </div>
  );
}
