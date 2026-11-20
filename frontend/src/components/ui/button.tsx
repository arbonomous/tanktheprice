import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-1.5 whitespace-nowrap rounded-md text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-sky-500 disabled:pointer-events-none disabled:opacity-50 cursor-pointer",
  {
    variants: {
      variant: {
        default: "bg-sky-500/15 text-sky-300 border border-sky-500/35 hover:bg-sky-500/25",
        secondary: "bg-[#162033] text-slate-200 border border-slate-700/80 hover:bg-[#1E2B44] hover:text-white",
        ghost: "text-slate-400 hover:bg-slate-800/70 hover:text-slate-100",
        danger: "bg-red-500/15 text-red-300 border border-red-500/35 hover:bg-red-500/25",
        emerald: "bg-emerald-500/15 text-emerald-300 border border-emerald-500/35 hover:bg-emerald-500/25",
      },
      size: {
        default: "h-8 px-3 py-1.5",
        sm: "h-7 px-2.5 text-[11px]",
        xs: "h-6 px-2 text-[11px]",
        icon: "h-7 w-7",
      },
    },
    defaultVariants: {
      variant: "secondary",
      size: "default",
    },
  }
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, ...props }, ref) => (
    <button ref={ref} className={cn(buttonVariants({ variant, size, className }))} {...props} />
  )
);
Button.displayName = "Button";
