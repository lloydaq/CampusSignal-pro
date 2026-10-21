import { cva, type VariantProps } from "class-variance-authority";
import type { ButtonHTMLAttributes } from "react";

import { cn } from "@/lib/utils";

/**
 * Button variants and sizes from Design.md §6 (shadcn/ui pattern, project tokens only).
 * Touch screens get 44 px targets (PRD §18); mouse layouts keep the 32/40 px sizes.
 */
const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 rounded-sm font-medium whitespace-nowrap transition-colors disabled:cursor-not-allowed disabled:opacity-60 pointer-coarse:min-h-11 [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        primary: "bg-primary text-on-primary hover:bg-primary-hover",
        secondary: "border border-border-strong bg-surface text-fg hover:bg-surface-sunken",
        ghost: "text-fg hover:bg-surface-sunken",
        destructive: "bg-danger text-on-danger hover:opacity-90",
      },
      size: {
        sm: "h-8 px-3 text-sm",
        md: "h-10 px-4 text-sm",
      },
    },
    defaultVariants: { variant: "primary", size: "md" },
  },
);

export type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & VariantProps<typeof buttonVariants>;

export function Button({ className, variant, size, type = "button", ...props }: ButtonProps) {
  return <button type={type} className={cn(buttonVariants({ variant, size }), className)} {...props} />;
}
