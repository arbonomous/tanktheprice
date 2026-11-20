import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider font-mono border",
  {
    variants: {
      variant: {
        neutral: "bg-slate-800/90 text-slate-300 border-slate-700",
        emerald: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
        sky: "bg-sky-500/15 text-sky-300 border-sky-500/30",
        amber: "bg-amber-500/15 text-amber-300 border-amber-500/30",
        red: "bg-red-500/15 text-red-300 border-red-500/35",
      },
    },
    defaultVariants: {
      variant: "neutral",
    },
  }
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}
