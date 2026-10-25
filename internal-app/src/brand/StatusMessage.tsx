import type { ReactNode } from "react";

export type StatusVariant = "positive" | "warning" | "critical" | "neutral";

// One icon per status, so meaning never rests on colour alone (the text label is always shown beside it).
const ICONS: Record<StatusVariant, ReactNode> = {
  positive: <path d="M5 12.5l4.5 4.5L19 7.5" />,
  warning: <path d="M12 4l9 16H3L12 4zM12 10v5M12 17.5v.5" />,
  critical: <path d="M12 3a9 9 0 100 18 9 9 0 000-18zM12 7.5v6M12 16v.5" />,
  neutral: <path d="M12 3a9 9 0 100 18 9 9 0 000-18zM12 11v6M12 7.5v.5" />,
};

type Props = { variant: StatusVariant; label: string; children?: ReactNode };

/** A status message in the brand's four styles: icon, a visible text label, then the message. */
export function StatusMessage({ variant, label, children }: Props) {
  return (
    <div className={`status status-${variant}`} role={variant === "critical" ? "alert" : undefined}>
      <svg className="status-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
        {ICONS[variant]}
      </svg>
      <strong className="status-label">{label}</strong>
      {children !== undefined && <span className="status-text">{children}</span>}
    </div>
  );
}
