import type { ButtonHTMLAttributes, ReactNode } from "react";
import { cn } from "../../lib/utils";

type Variant = "primary" | "ghost" | "soft";

const styles: Record<Variant, string> = {
  primary: "bg-primary text-white hover:bg-primary/90 shadow-bubble",
  ghost: "bg-transparent text-muted hover:text-primary hover:bg-primary/10",
  soft: "bg-primary/10 text-primary-dark border border-lineSoft hover:bg-primary/15",
};

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  children: ReactNode;
}

export function Button({ variant = "primary", className, children, ...rest }: Props) {
  return (
    <button
      className={cn(
        "inline-flex items-center justify-center gap-2 rounded-xl px-4 py-2 text-sm font-medium",
        "transition-all duration-150 disabled:opacity-50 disabled:cursor-not-allowed",
        styles[variant],
        className,
      )}
      {...rest}
    >
      {children}
    </button>
  );
}
