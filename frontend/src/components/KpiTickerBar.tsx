"use client";

import React from "react";
import {
  Activity,
  Anchor,
  ArrowDownRight,
  ArrowUpRight,
  Database,
  Radio,
  RefreshCw,
  ShieldAlert,
  TrendingDown,
  TrendingUp,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import type { DashboardSummary } from "@/lib/types";
import { cn, formatSigned, formatUsd, formatUtcTime } from "@/lib/utils";

interface KpiTickerBarProps {
  summary: DashboardSummary | null;
  refreshing: boolean;
  onRefresh: () => void;
  onModeChange: (mode: "auto" | "live" | "simulator") => void;
}

export function KpiTickerBar({ summary, refreshing, onRefresh, onModeChange }: KpiTickerBarProps) {
  const shockScore = summary?.supply_shock_score ?? 0;
  const shockTone =
    shockScore >= 25
      ? "text-red-400"
      : shockScore >= 10
        ? "text-amber-400"
        : shockScore <= -15
          ? "text-sky-400"
          : "text-emerald-400";

  const biasVariant =
    summary?.brent_bias === "BULLISH"
      ? "emerald"
      : summary?.brent_bias === "BEARISH"
        ? "red"
        : "neutral";

  const liveAdaptersCount = summary?.adapters.filter((a) => a.status === "LIVE").length ?? 0;

  return (
    <header
      id="kpi-ticker-bar"
      className="sticky top-0 z-30 border-b border-slate-800/90 bg-[#0B0F19]/95 backdrop-blur-md"
    >
      {/* Top Brand & Utility Strip */}
      <div className="flex flex-wrap items-center justify-between gap-2 px-4 py-2 border-b border-slate-800/70">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <div className="h-7 w-7 rounded bg-sky-500/15 border border-sky-500/35 flex items-center justify-center">
              <Anchor className="h-4 w-4 text-sky-400" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-sm font-bold tracking-[0.14em] text-slate-100 uppercase">
                  HormuzFlow
                </h1>
                <span className="text-[10px] font-mono uppercase tracking-wider px-1.5 py-0.5 rounded bg-slate-800/90 text-slate-400 border border-slate-700/80">
                  24.0°–28.0°N / 55.0°–58.5°E
                </span>
              </div>
              <p className="text-[11px] text-slate-400 leading-tight">
                Strait of Hormuz Maritime Intelligence &amp; Crude Oil Price-Swing Terminal
              </p>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <Popover>
            <PopoverTrigger asChild>
              <Button id="feed-status-btn" variant="secondary" size="sm" className="font-mono text-[11px]">
                <Database className="h-3.5 w-3.5 text-sky-400" />
                <span>
                  FEEDS: {liveAdaptersCount > 0 ? `${liveAdaptersCount} LIVE` : "SIM"} ·{" "}
                  {(summary?.feed_mode || "auto").toUpperCase()}
                </span>
              </Button>
            </PopoverTrigger>
            <PopoverContent align="end" className="w-[420px]">
              <div className="flex items-center justify-between pb-2.5 mb-2.5 border-b border-slate-800">
                <div>
                  <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-200">
                    Data Ingestion Adapters
                  </h3>
                  <p className="text-[11px] text-slate-400">
                    Zero-key fallback active; add API keys in <code className="text-sky-300">.env.local</code> to upgrade
                  </p>
                </div>
                <div className="flex items-center gap-1">
                  {(["auto", "simulator"] as const).map((m) => (
                    <Button
                      key={m}
                      size="xs"
                      variant={summary?.feed_mode === m ? "default" : "ghost"}
                      onClick={() => onModeChange(m)}
                      className="uppercase font-mono"
                    >
                      {m}
                    </Button>
                  ))}
                </div>
              </div>
              <div className="space-y-1.5 max-h-64 overflow-y-auto pr-1">
                {(summary?.adapters || []).map((ad) => (
                  <div
                    key={`${ad.category}-${ad.name}`}
                    className="flex items-start justify-between gap-2 rounded border border-slate-800/80 bg-[#0B0F19] px-2.5 py-2"
                  >
                    <div className="min-w-0">
                      <div className="flex items-center gap-1.5">
                        <span className="text-xs font-mono font-semibold text-slate-200">{ad.name}</span>
                        <span className="text-[10px] uppercase text-slate-500">{ad.category}</span>
                      </div>
                      <p className="text-[11px] text-slate-400 truncate mt-0.5">{ad.message}</p>
                    </div>
                    <Badge
                      variant={
                        ad.status === "LIVE"
                          ? "emerald"
                          : ad.status === "FALLBACK_SIMULATOR"
                            ? "sky"
                            : ad.status === "DEGRADED"
                              ? "amber"
                              : "neutral"
                      }
                      className="shrink-0"
                    >
                      {ad.status.replace("_", " ")}
                    </Badge>
                  </div>
                ))}
              </div>
              {summary?.last_refreshed && (
                <div className="mt-2.5 pt-2 border-t border-slate-800 flex items-center justify-between text-[10px] font-mono text-slate-500">
                  <span>LAST SYNC: {formatUtcTime(summary.last_refreshed)}</span>
                  <span>BACKTEST ACC: {summary.backtest_accuracy_pct.toFixed(1)}%</span>
                </div>
              )}
            </PopoverContent>
          </Popover>

          <Button
            id="refresh-feeds-btn"
            variant="default"
            size="sm"
            onClick={onRefresh}
            disabled={refreshing}
            className="font-mono"
          >
            <RefreshCw className={cn("h-3.5 w-3.5", refreshing && "animate-spin")} />
            <span>{refreshing ? "SYNCING" : "REFRESH"}</span>
          </Button>
        </div>
      </div>

      {/* High-Density Bloomberg KPI Ticker Row */}
      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 divide-y md:divide-y-0 md:divide-x divide-slate-800/80">
        {/* Brent Crude */}
        <div id="kpi-brent" className="px-4 py-2.5 flex flex-col justify-between">
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-mono uppercase tracking-wider text-slate-400">
              Brent Crude · BZ=F
            </span>
            <span className="text-[10px] font-mono text-slate-500">{summary?.brent.source || "—"}</span>
          </div>
          <div className="mt-1 flex items-baseline justify-between gap-2">
            <span className="text-lg font-mono font-semibold tabular-nums text-slate-100">
              {summary ? formatUsd(summary.brent.price) : "—"}
            </span>
            {summary && (
              <span
                className={cn(
                  "inline-flex items-center text-xs font-mono font-medium tabular-nums",
                  summary.brent.change_24h >= 0 ? "text-emerald-400" : "text-red-400"
                )}
              >
                {summary.brent.change_24h >= 0 ? (
                  <ArrowUpRight className="h-3.5 w-3.5" />
                ) : (
                  <ArrowDownRight className="h-3.5 w-3.5" />
                )}
                {formatSigned(summary.brent.change_24h_pct, 2, "%")}
              </span>
            )}
          </div>
        </div>

        {/* WTI Crude */}
        <div id="kpi-wti" className="px-4 py-2.5 flex flex-col justify-between">
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-mono uppercase tracking-wider text-slate-400">
              WTI Crude · CL=F
            </span>
            <span className="text-[10px] font-mono text-slate-500">
              SPREAD {summary ? formatUsd(summary.brent.price - summary.wti.price) : "—"}
            </span>
          </div>
          <div className="mt-1 flex items-baseline justify-between gap-2">
            <span className="text-lg font-mono font-semibold tabular-nums text-slate-100">
              {summary ? formatUsd(summary.wti.price) : "—"}
            </span>
            {summary && (
              <span
                className={cn(
                  "inline-flex items-center text-xs font-mono font-medium tabular-nums",
                  summary.wti.change_24h >= 0 ? "text-emerald-400" : "text-red-400"
                )}
              >
                {summary.wti.change_24h >= 0 ? (
                  <ArrowUpRight className="h-3.5 w-3.5" />
                ) : (
                  <ArrowDownRight className="h-3.5 w-3.5" />
                )}
                {formatSigned(summary.wti.change_24h_pct, 2, "%")}
              </span>
            )}
          </div>
        </div>

        {/* 24h Outbound Laden Tankers */}
        <div id="kpi-outbound" className="px-4 py-2.5 flex flex-col justify-between">
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-mono uppercase tracking-wider text-slate-400">
              24h Outbound Laden
            </span>
            <span className="text-[10px] font-mono text-emerald-400/90">090°–160° &gt;12m</span>
          </div>
          <div className="mt-1 flex items-baseline justify-between gap-2">
            <span className="text-lg font-mono font-semibold tabular-nums text-emerald-300">
              {summary ? `${summary.outbound_laden_24h}` : "—"}{" "}
              <span className="text-xs font-normal text-slate-400">tankers</span>
            </span>
            <span className="text-xs font-mono tabular-nums text-slate-300">
              {summary ? `${summary.outbound_barrels_24h_mbbl.toFixed(1)} Mbbl` : "—"}
            </span>
          </div>
        </div>

        {/* 7d Flow Delta % */}
        <div id="kpi-flow-delta" className="px-4 py-2.5 flex flex-col justify-between">
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-mono uppercase tracking-wider text-slate-400">
              7d Flow Delta vs 30d
            </span>
            <span className="text-[10px] font-mono text-slate-500">
              CONG {summary ? `${summary.congestion_index.toFixed(0)}/100` : "—"}
            </span>
          </div>
          <div className="mt-1 flex items-baseline justify-between gap-2">
            <span
              className={cn(
                "text-lg font-mono font-semibold tabular-nums",
                (summary?.flow_delta_7d_pct ?? 0) < -5
                  ? "text-amber-400"
                  : (summary?.flow_delta_7d_pct ?? 0) > 5
                    ? "text-emerald-400"
                    : "text-slate-100"
              )}
            >
              {summary ? formatSigned(summary.flow_delta_7d_pct, 1, "%") : "—"}
            </span>
            <span className="text-[11px] font-mono tabular-nums text-slate-400">
              {summary
                ? `${summary.rolling_7d_avg_count.toFixed(1)} / ${summary.baseline_30d_avg_count.toFixed(1)}`
                : "—"}
            </span>
          </div>
        </div>

        {/* Active AIS-Dark Vessels */}
        <div id="kpi-dark-vessels" className="px-4 py-2.5 flex flex-col justify-between">
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-mono uppercase tracking-wider text-slate-400">
              Active AIS-Dark Vessels
            </span>
            <Radio className="h-3.5 w-3.5 text-red-400" />
          </div>
          <div className="mt-1 flex items-baseline justify-between gap-2">
            <span className="text-lg font-mono font-semibold tabular-nums text-red-400">
              {summary ? summary.active_ais_dark_vessels : "—"}{" "}
              <span className="text-xs font-normal text-slate-400">
                ({summary?.corridor_dark_vessels ?? 0} in corr)
              </span>
            </span>
            <Badge variant="red" className="text-[9px]">
              <ShieldAlert className="h-2.5 w-2.5" />
              {summary?.sanctioned_active_count ?? 0} SANC
            </Badge>
          </div>
        </div>

        {/* Composite Supply Shock Score + Bias */}
        <div id="kpi-supply-shock" className="px-4 py-2.5 flex flex-col justify-between bg-[#101829]/90">
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-mono uppercase tracking-wider text-slate-300">
              Supply Shock &amp; 72h Bias
            </span>
            <Activity className="h-3.5 w-3.5 text-amber-400" />
          </div>
          <div className="mt-1 flex items-center justify-between gap-2">
            <span className={cn("text-lg font-mono font-bold tabular-nums", shockTone)}>
              {summary ? formatSigned(summary.supply_shock_score, 1) : "—"}
            </span>
            {summary && (
              <div className="flex items-center gap-1.5">
                <Badge variant={biasVariant}>
                  {summary.brent_bias === "BULLISH" ? (
                    <TrendingUp className="h-3 w-3" />
                  ) : summary.brent_bias === "BEARISH" ? (
                    <TrendingDown className="h-3 w-3" />
                  ) : null}
                  {summary.brent_bias}
                </Badge>
                <span className="text-xs font-mono tabular-nums text-slate-200">
                  {formatSigned(summary.predicted_72h_brent_pct, 2, "%")}
                </span>
              </div>
            )}
          </div>
        </div>
      </div>
    </header>
  );
}
