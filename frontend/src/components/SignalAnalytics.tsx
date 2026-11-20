"use client";

import React from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Activity, Cpu, Radar, Target } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { SignalsOverview } from "@/lib/types";
import { cn, formatSigned } from "@/lib/utils";

interface SignalAnalyticsProps {
  signals: SignalsOverview | null;
}

export function SignalAnalytics({ signals }: SignalAnalyticsProps) {
  const shock = signals?.supply_shock_score ?? 0;
  // Convert -100..+100 into 0..100% slider bar position
  const gaugePct = Math.max(0, Math.min(100, (shock + 100) / 2));

  const lagData = (signals?.lag_correlations || []).map((lc) => ({
    label: `${lc.lag_days}D LAG`,
    brentCorr: Number(lc.brent_corr.toFixed(3)),
    wtiCorr: Number(lc.wti_corr.toFixed(3)),
    brentProb: lc.brent_up_prob_pct,
    wtiProb: lc.wti_up_prob_pct,
  }));

  const shockSeries = (signals?.daily_signals || []).slice(-30).map((d) => ({
    date: d.date.slice(5),
    shock: d.supply_shock_score,
    congestion: d.congestion_index,
  }));

  const backtestData = (signals?.backtest_series || []).slice(-20).map((b) => ({
    date: b.date.slice(5),
    predicted: b.predicted_3d_return_pct,
    actual: b.actual_3d_return_pct,
    hit: b.hit,
  }));

  return (
    <section
      id="signal-analytics-panel"
      className="terminal-panel rounded-lg overflow-hidden flex flex-col h-[520px] xl:h-[560px]"
    >
      {/* Header */}
      <div className="flex items-center justify-between gap-2 px-4 py-2.5 border-b border-slate-800/90 bg-[#0D1321]/80">
        <div className="flex items-center gap-2">
          <Cpu className="h-4 w-4 text-amber-400" />
          <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-100">
            Quantitative Signal Engine &amp; Backtester
          </h2>
        </div>
        <Badge variant="sky" className="tabular-nums">
          GBR + Z-SCORE
        </Badge>
      </div>

      {/* Composite Supply Shock Gauge + 24h-72h Prediction Strip */}
      <div className="px-4 py-3 border-b border-slate-800/80 bg-[#0B0F19]/80 space-y-3">
        <div className="flex items-center justify-between gap-3">
          <div>
            <div className="text-[10px] font-mono uppercase tracking-wider text-slate-400">
              Hormuz Supply Shock Score (-100 to +100)
            </div>
            <div className="mt-0.5 flex items-baseline gap-2">
              <span
                className={cn(
                  "text-2xl font-mono font-bold tabular-nums",
                  shock >= 25 ? "text-red-400" : shock >= 10 ? "text-amber-400" : shock <= -15 ? "text-sky-400" : "text-emerald-400"
                )}
              >
                {formatSigned(shock, 1)}
              </span>
              <Badge
                variant={
                  signals?.brent_bias === "BULLISH"
                    ? "emerald"
                    : signals?.brent_bias === "BEARISH"
                      ? "red"
                      : "neutral"
                }
              >
                {signals?.brent_bias || "NEUTRAL"} OIL BIAS
              </Badge>
            </div>
          </div>

          <div className="text-right">
            <div className="text-[10px] font-mono uppercase text-slate-400">72h Brent Forecast (80% CI)</div>
            <div className="mt-0.5 text-sm font-mono font-semibold text-slate-100 tabular-nums">
              {signals ? formatSigned(signals.predicted_72h_brent_pct, 2, "%") : "—"}{" "}
              <span className="text-[11px] font-normal text-slate-400">
                [{signals ? formatSigned(signals.confidence_low_pct, 1) : "—"}% to{" "}
                {signals ? formatSigned(signals.confidence_high_pct, 1) : "—"}%]
              </span>
            </div>
          </div>
        </div>

        {/* Visual -100 to +100 bar */}
        <div>
          <div className="relative h-2 rounded-full bg-gradient-to-r from-sky-500/70 via-slate-700 to-red-500/80 overflow-visible">
            <div className="absolute left-1/2 top-0 bottom-0 w-px bg-slate-300/60" />
            <div
              className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 h-3.5 w-3.5 rounded-full bg-white border-2 border-[#0B0F19] shadow"
              style={{ left: `${gaugePct}%` }}
            />
          </div>
          <div className="mt-1 flex justify-between text-[9px] font-mono text-slate-500">
            <span>-100 OVERSUPPLY</span>
            <span>0 BALANCED</span>
            <span>+100 CHOKE SQUEEZE</span>
          </div>
        </div>

        {/* 3 Core Signal Sub-Metrics */}
        <div className="grid grid-cols-3 gap-2 pt-0.5">
          <div className="rounded border border-slate-800/90 bg-[#101726] px-2.5 py-1.5">
            <div className="text-[9px] font-mono uppercase text-slate-400">7d Flow Z-Score</div>
            <div className="text-xs font-mono font-semibold text-slate-100 tabular-nums mt-0.5">
              {signals ? formatSigned(signals.flow_metrics.flow_zscore, 2, "σ") : "—"}
            </div>
          </div>
          <div className="rounded border border-slate-800/90 bg-[#101726] px-2.5 py-1.5">
            <div className="text-[9px] font-mono uppercase text-slate-400">Congestion Idx</div>
            <div className="text-xs font-mono font-semibold text-amber-300 tabular-nums mt-0.5">
              {signals ? `${signals.congestion_metrics.congestion_index.toFixed(1)} / 100` : "—"}
            </div>
          </div>
          <div className="rounded border border-slate-800/90 bg-[#101726] px-2.5 py-1.5">
            <div className="text-[9px] font-mono uppercase text-slate-400">Dark-Fleet Spike</div>
            <div className="text-xs font-mono font-semibold text-red-400 tabular-nums mt-0.5">
              {signals ? `${signals.dark_fleet_metrics.dark_fleet_spike_score.toFixed(1)} / 100` : "—"}
            </div>
          </div>
        </div>
      </div>

      {/* Tabbed Signal Visualizations */}
      <Tabs defaultValue="lags" className="flex-1 flex flex-col min-h-0 p-3.5">
        <div className="flex items-center justify-between gap-2 mb-2.5">
          <TabsList>
            <TabsTrigger value="lags">LAG CORR (1D/3D/7D)</TabsTrigger>
            <TabsTrigger value="shock">SHOCK TIMELINE</TabsTrigger>
            <TabsTrigger value="backtest">BACKTEST</TabsTrigger>
          </TabsList>
          <div className="text-[10px] font-mono text-slate-400 tabular-nums">
            HIT RATE:{" "}
            <span className="text-emerald-400 font-semibold">
              {signals ? `${signals.backtest_accuracy_pct.toFixed(1)}%` : "—"}
            </span>
          </div>
        </div>

        {/* Tab 1: Rolling Lag Correlations & Up-Move Probabilities */}
        <TabsContent value="lags" className="flex-1 flex flex-col min-h-0 space-y-2.5">
          <div className="flex-1 min-h-[150px]">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={lagData} margin={{ top: 8, right: 8, left: -22, bottom: 0 }}>
                <CartesianGrid stroke="#1E293B" strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="label" tick={{ fill: "#94A3B8", fontSize: 10 }} axisLine={false} tickLine={false} />
                <YAxis
                  domain={[-1, 1]}
                  tick={{ fill: "#64748B", fontSize: 10 }}
                  axisLine={false}
                  tickLine={false}
                />
                <ReferenceLine y={0} stroke="#475569" />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "#0D1321",
                    borderColor: "#334155",
                    fontSize: "11px",
                    fontFamily: "monospace",
                  }}
                />
                <Bar dataKey="brentCorr" name="Brent r" fill="#10B981" radius={[3, 3, 0, 0]} />
                <Bar dataKey="wtiCorr" name="WTI r" fill="#38BDF8" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>

          <div className="grid grid-cols-3 gap-2">
            {(signals?.lag_correlations || []).map((lc) => (
              <div
                key={lc.lag_days}
                className="rounded border border-slate-800 bg-[#0B0F19] px-2.5 py-2 text-center"
              >
                <div className="text-[10px] font-mono text-slate-400">{lc.lag_days}D FWD UP PROB</div>
                <div className="mt-0.5 text-xs font-mono font-semibold text-emerald-300 tabular-nums">
                  BZ {lc.brent_up_prob_pct.toFixed(0)}%
                </div>
                <div className="text-[10px] font-mono text-sky-300 tabular-nums">
                  CL {lc.wti_up_prob_pct.toFixed(0)}%
                </div>
              </div>
            ))}
          </div>
        </TabsContent>

        {/* Tab 2: 30-Day Supply Shock Score Timeline */}
        <TabsContent value="shock" className="flex-1 flex flex-col min-h-0">
          <div className="flex-1 min-h-[180px]">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={shockSeries} margin={{ top: 8, right: 8, left: -22, bottom: 0 }}>
                <defs>
                  <linearGradient id="shockFill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#F59E0B" stopOpacity={0.4} />
                    <stop offset="95%" stopColor="#F59E0B" stopOpacity={0.02} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke="#1E293B" strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="date" tick={{ fill: "#94A3B8", fontSize: 9 }} axisLine={false} tickLine={false} />
                <YAxis domain={[-100, 100]} tick={{ fill: "#64748B", fontSize: 10 }} axisLine={false} tickLine={false} />
                <ReferenceLine y={0} stroke="#475569" />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "#0D1321",
                    borderColor: "#334155",
                    fontSize: "11px",
                    fontFamily: "monospace",
                  }}
                />
                <Area
                  type="monotone"
                  dataKey="shock"
                  name="Supply Shock Score"
                  stroke="#F59E0B"
                  strokeWidth={2}
                  fill="url(#shockFill)"
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
          <div className="mt-2 flex items-center justify-between text-[10px] font-mono text-slate-400">
            <span className="inline-flex items-center gap-1">
              <Radar className="h-3 w-3 text-amber-400" /> Avg Speed:{" "}
              {signals?.congestion_metrics.avg_transit_speed_knots.toFixed(1)} kn
            </span>
            <span className="inline-flex items-center gap-1">
              <Activity className="h-3 w-3 text-sky-400" /> Loitering:{" "}
              {signals?.congestion_metrics.loitering_vessels_count} tankers
            </span>
          </div>
        </TabsContent>

        {/* Tab 3: Walk-Forward Backtest */}
        <TabsContent value="backtest" className="flex-1 flex flex-col min-h-0 space-y-2">
          <div className="flex-1 min-h-[155px]">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={backtestData} margin={{ top: 8, right: 8, left: -22, bottom: 0 }}>
                <CartesianGrid stroke="#1E293B" strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="date" tick={{ fill: "#94A3B8", fontSize: 9 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: "#64748B", fontSize: 10 }} axisLine={false} tickLine={false} />
                <ReferenceLine y={0} stroke="#475569" />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "#0D1321",
                    borderColor: "#334155",
                    fontSize: "11px",
                    fontFamily: "monospace",
                  }}
                />
                <Bar dataKey="actual" name="Actual 3d %" radius={[2, 2, 0, 0]}>
                  {backtestData.map((entry, idx) => (
                    <Cell key={idx} fill={entry.hit ? "#10B981" : "#EF4444"} fillOpacity={0.85} />
                  ))}
                </Bar>
                <Bar dataKey="predicted" name="Pred 3d %" fill="#38BDF8" fillOpacity={0.55} radius={[2, 2, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>

          <div className="grid grid-cols-3 gap-2 text-[10px] font-mono">
            <div className="rounded border border-slate-800 bg-[#0B0F19] px-2 py-1.5">
              <div className="text-slate-400">DIRECTIONAL ACC</div>
              <div className="text-xs font-semibold text-emerald-400 mt-0.5 tabular-nums">
                {signals ? `${signals.backtest_accuracy_pct.toFixed(1)}%` : "—"}
              </div>
            </div>
            <div className="rounded border border-slate-800 bg-[#0B0F19] px-2 py-1.5">
              <div className="text-slate-400">SIGNAL SHARPE</div>
              <div className="text-xs font-semibold text-sky-300 mt-0.5 tabular-nums">
                {signals ? signals.signal_sharpe_estimate.toFixed(2) : "—"}
              </div>
            </div>
            <div className="rounded border border-slate-800 bg-[#0B0F19] px-2 py-1.5">
              <div className="text-slate-400 flex items-center gap-1">
                <Target className="h-2.5 w-2.5" /> WINDOWS
              </div>
              <div className="text-xs font-semibold text-slate-200 mt-0.5 tabular-nums">
                {signals?.backtest_sample_size ?? 0} OOS
              </div>
            </div>
          </div>
        </TabsContent>
      </Tabs>
    </section>
  );
}
