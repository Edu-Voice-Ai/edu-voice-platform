import * as React from "react";
import { ArrowUpRight, ArrowDownRight } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

export interface StatCardProps {
  title: string;
  value: string | number;
  change?: {
    value: string;
    isPositive: boolean;
    period?: string;
  };
  icon: React.ReactNode;
  iconBgColor?: string;
  subtitle?: string;
  className?: string;
}

export function StatCard({
  title,
  value,
  change,
  icon,
  iconBgColor = "bg-primary/10 text-primary",
  subtitle,
  className,
}: StatCardProps) {
  return (
    <Card
      className={cn(
        "relative overflow-hidden transition-all duration-200 hover:shadow-md",
        className
      )}
    >
      <CardContent className="p-5">
        <div className="flex items-center justify-between">
          <p className="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
            {title}
          </p>
          <div
            className={cn(
              "flex h-10 w-10 items-center justify-center rounded-xl transition-transform hover:scale-105",
              iconBgColor
            )}
          >
            {icon}
          </div>
        </div>

        <div className="mt-3 flex items-baseline gap-2">
          <h4 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-slate-100">
            {value}
          </h4>
        </div>

        {(change || subtitle) && (
          <div className="mt-2 flex items-center gap-1.5 text-xs">
            {change && (
              <span
                className={cn(
                  "inline-flex items-center font-semibold",
                  change.isPositive ? "text-emerald-600 dark:text-emerald-400" : "text-red-500"
                )}
              >
                {change.isPositive ? (
                  <ArrowUpRight className="mr-0.5 h-3.5 w-3.5" />
                ) : (
                  <ArrowDownRight className="mr-0.5 h-3.5 w-3.5" />
                )}
                {change.value}
              </span>
            )}
            <span className="text-muted-foreground">
              {change?.period || subtitle}
            </span>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
