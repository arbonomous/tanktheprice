"use client";

import * as React from "react";
import * as SliderPrimitive from "@radix-ui/react-slider";
import { cn } from "@/lib/utils";

export const Slider = React.forwardRef<
  React.ComponentRef<typeof SliderPrimitive.Root>,
  React.ComponentPropsWithoutRef<typeof SliderPrimitive.Root> & { accent?: "emerald" | "amber" | "red" | "sky" }
>(({ className, accent = "sky", ...props }, ref) => {
  const rangeColor = {
    emerald: "bg-emerald-500",
    amber: "bg-amber-500",
    red: "bg-red-500",
    sky: "bg-sky-500",
  }[accent];

  const thumbBorder = {
    emerald: "border-emerald-400",
    amber: "border-amber-400",
    red: "border-red-400",
    sky: "border-sky-400",
  }[accent];

  return (
    <SliderPrimitive.Root
      ref={ref}
      className={cn("relative flex w-full touch-none select-none items-center py-1.5 cursor-pointer", className)}
      {...props}
    >
      <SliderPrimitive.Track className="relative h-1.5 w-full grow overflow-hidden rounded-full bg-slate-800 border border-slate-700/70">
        <SliderPrimitive.Range className={cn("absolute h-full", rangeColor)} />
      </SliderPrimitive.Track>
      <SliderPrimitive.Thumb
        className={cn(
          "block h-4 w-4 rounded-full border-2 bg-[#0B0F19] shadow-md transition-transform hover:scale-110 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500",
          thumbBorder
        )}
      />
    </SliderPrimitive.Root>
  );
});
Slider.displayName = "Slider";
