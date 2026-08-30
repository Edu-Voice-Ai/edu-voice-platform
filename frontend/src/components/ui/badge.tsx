import * as React from "react";
import { cn } from "@/lib/utils";

export interface BadgeProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?:
    | "default"
    | "secondary"
    | "destructive"
    | "outline"
    | "success"
    | "warning"
    | "indigo"
    | "teal";
}

function Badge({ className, variant = "default", ...props }: BadgeProps) {
  const variantStyles = {
    default:
      "border-transparent bg-primary text-primary-foreground hover:bg-primary/80",
    secondary:
      "border-transparent bg-slate-100 text-slate-800 dark:bg-slate-800 dark:text-slate-200",
    destructive:
      "border-transparent bg-red-100 text-red-700 dark:bg-red-950/50 dark:text-red-400",
    outline: "text-foreground border-slate-200 dark:border-slate-800",
    success:
      "border-transparent bg-emerald-100 text-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-400 font-medium",
    warning:
      "border-transparent bg-amber-100 text-amber-800 dark:bg-amber-950/50 dark:text-amber-400 font-medium",
    indigo:
      "border-transparent bg-indigo-100 text-indigo-800 dark:bg-indigo-950/50 dark:text-indigo-300 font-medium",
    teal: "border-transparent bg-teal-100 text-teal-800 dark:bg-teal-950/50 dark:text-teal-300 font-medium",
  };

  return (
    <div
      className={cn(
        "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2",
        variantStyles[variant],
        className
      )}
      {...props}
    />
  );
}

export { Badge };
