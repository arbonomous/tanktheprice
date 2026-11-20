"use client";

import React, { useEffect, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Flame, RotateCcw, SlidersHorizontal } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Slider } from "@/components/ui/slider";
import { hormuzApi } from "@/lib/api";
import type { StressTestResult } from "@/lib/types";
import { formatSigned, formatUsd } from "@/lib/utils";

interface StressTestPanelProps {
  initialResult: StressTestResult | null;
}

export function StressTestPanel({ initialResult }: StressTestPanelProps) {
  const [vlccDrop, setVlccDrop] = useState<number>(30);
  const [aisMultiplier, setAisMultiplier] = useState<number>(2.0);
  const [congestionSurge, setCongestionSurge] = useState<number>(25);
  const [durationDays, setDurationDays] = useState<number>(5);
  const [result, setResult] = useState<StressTestResult | null>(initialResult);
  const [computing, setComputing] = useState(false);

  useEffect(() => {
    if (initialResult && !result) {
      setResult(initialResult);
    }
  }, [initialResult, result]);

  useEffect(() => {
    let cancelled = false;
    const timer = setTimeout(async () => {
      setComputing(true);
      try {
        const res = await hormuzApi.runStressTest({
          vlcc_drop_pct: vlccDrop,
          ais_spoofing_multiplier: aisMultiplier,
          congestion_surge_pct: congestionSurge,
          duration_days: durationDays,
        });
        if (!cancelled) {
          setResult(res);
        }
      } catch {
        // Keep last valid simulation result if transient network issue occurs
      } finally {
        if (!cancelled) setComputing(false);
      }
    }, 120);

    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [vlccDrop, aisMultiplier, congestionSurge, durationDays]);

  const applyPreset = (drop: number, ais: number, cong: number, dur: number) => {
    setVlccDrop(drop);
    setAisMultiplier(ais);
    setCongestionSurge(cong);
    setDurationDays(dur);
  };

  const regimeVariant =
    (result?.projected_supply_shock_score ?? 0) >= 75
      ? "red"
      : (result?.projected_supply_shock_score ?? 0) >= 45
        ? "amber"
        : "sky";

  return (
    <section id="stress-test-panel" className="terminal-panel rounded-lg overflow-hidden flex flex-col">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-2 px-4 py-2.5 border-b border-slate-800/90 bg-[#0D1321]/80">
        <div className="flex items-center gap-2">
          <SlidersHorizontal className="h-4 w-4 text-red-400" />
          <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-100">
            Scenario Stress-Test Simulator
          </h2>
          {result && <Badge variant={regimeVariant}>{result.risk_regime}</Badge>}
        </div>

        <div className="flex flex-wrap items-center gap-1.5">
          <Button
            id="preset-vlcc-15"
            size="xs"
            variant={vlccDrop === 15 ? "default" : "secondary"}
            onClick={() => applyPreset(15, 1.5, 15, 4)}
            className="font-mono"
          >
            -15% VLCC
          </Button>
          <Button
            id="preset-vlcc-30"
            size="xs"
            variant={vlccDrop === 30 ? "default" : "secondary"}
            onClick={() => applyPreset(30, 2.0, 25, 5)}
            className="font-mono"
          >
            -30% VLCC
          </Button>
          <Button
            id="preset-vlcc-50"
            size="xs"
            variant={vlccDrop === 50 ? "danger" : "secondary"}
            onClick={() => applyPreset(50, 3.5, 65, 7)}
            className="font-mono"
          >
            <Flame className="h-3 w-3" /> -50% CHOKE
          </Button>
          <Button
            id="preset-reset"
            size="xs"
            variant="ghost"
            onClick={() => applyPreset(0, 1.0, 0, 1)}
            title="Reset to baseline"
          >
            <RotateCcw className="h-3 w-3" />
          </Button>
        </div>
      </div>

      {/* Body Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 p-4">
        {/* Left: Interactive Sliders */}
        <div className="lg:col-span-5 space-y-4">
          {/* Slider 1: VLCC Drop */}
          <div className="space-y-1.5">
            <div className="flex items-center justify-between text-xs">
              <label htmlFor="slider-vlcc-drop" className="font-mono text-slate-300">
                Outbound VLCC Transit Drop
              </label>
              <span id="val-vlcc-drop" className="font-mono font-semibold text-red-400 tabular-nums">
                -{vlccDrop}%
              </span>
            </div>
            <Slider
              id="slider-vlcc-drop"
              min={0}
              max={60}
              step={1}
              value={[vlccDrop]}
              onValueChange={([v]) => setVlccDrop(v)}
              accent="red"
            />
            <div className="flex justify-between text-[9px] font-mono text-slate-500">
              <span>0% Baseline</span>
              <span>15%</span>
              <span>30%</span>
              <span>50% Severe</span>
              <span>60%</span>
            </div>
          </div>

          {/* Slider 2: AIS Spoofing / Dark-Fleet Spike */}
          <div className="space-y-1.5">
            <div className="flex items-center justify-between text-xs">
              <label htmlFor="slider-ais-spoof" className="font-mono text-slate-300">
                AIS Spoofing / Dark-Fleet Spike
              </label>
              <span id="val-ais-spoof" className="font-mono font-semibold text-amber-400 tabular-nums">
                {aisMultiplier.toFixed(1)}x baseline
              </span>
            </div>
            <Slider
              id="slider-ais-spoof"
              min={1}
              max={5}
              step={0.1}
              value={[aisMultiplier]}
              onValueChange={([v]) => setAisMultiplier(Number(v.toFixed(1)))}
              accent="amber"
            />
          </div>

          {/* Slider 3: TSS Congestion Surge */}
          <div className="space-y-1.5">
            <div className="flex items-center justify-between text-xs">
              <label htmlFor="slider-congestion" className="font-mono text-slate-300">
                TSS Congestion / Loitering Surge
              </label>
              <span className="font-mono font-semibold text-sky-400 tabular-nums">+{congestionSurge}%</span>
            </div>
            <Slider
              id="slider-congestion"
              min={0}
              max={100}
              step={5}
              value={[congestionSurge]}
              onValueChange={([v]) => setCongestionSurge(v)}
              accent="sky"
            />
          </div>

          {/* Slider 4: Disruption Duration */}
          <div className="space-y-1.5">
            <div className="flex items-center justify-between text-xs">
              <label htmlFor="slider-duration" className="font-mono text-slate-300">
                Choke Disruption Duration
              </label>
              <span className="font-mono font-semibold text-slate-200 tabular-nums">{durationDays} days</span>
            </div>
            <Slider
              id="slider-duration"
              min={1}
              max={14}
              step={1}
              value={[durationDays]}
              onValueChange={([v]) => setDurationDays(v)}
              accent="emerald"
            />
          </div>
        </div>

        {/* Right: Projected Price Impact Cards & 7-Day Curve */}
        <div className="lg:col-span-7 flex flex-col gap-3">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            <div className="rounded border border-emerald-500/30 bg-[#0B0F19] p-2.5">
              <div className="text-[9px] font-mono uppercase text-slate-400">Projected Brent</div>
              <div
                id="stress-brent-price"
                className="mt-0.5 text-base font-mono font-bold text-emerald-300 tabular-nums"
              >
                {result ? formatUsd(result.brent_projected_price) : "—"}
              </div>
              <div id="stress-brent-delta" className="text-[11px] font-mono text-emerald-400 tabular-nums">
                {result
                  ? `${formatSigned(result.brent_delta_usd, 2)} (${formatSigned(result.brent_delta_pct, 1, "%")})`
                  : "—"}
              </div>
            </div>

            <div className="rounded border border-sky-500/30 bg-[#0B0F19] p-2.5">
              <div className="text-[9px] font-mono uppercase text-slate-400">Projected WTI</div>
              <div
                id="stress-wti-price"
                className="mt-0.5 text-base font-mono font-bold text-sky-300 tabular-nums"
              >
                {result ? formatUsd(result.wti_projected_price) : "—"}
              </div>
              <div id="stress-wti-delta" className="text-[11px] font-mono text-sky-400 tabular-nums">
                {result
                  ? `${formatSigned(result.wti_delta_usd, 2)} (${formatSigned(result.wti_delta_pct, 1, "%")})`
                  : "—"}
              </div>
            </div>

            <div className="rounded border border-slate-800 bg-[#0B0F19] p-2.5">
              <div className="text-[9px] font-mono uppercase text-slate-400">Disrupted Supply</div>
              <div className="mt-0.5 text-base font-mono font-bold text-amber-300 tabular-nums">
                {result ? `${result.disrupted_mbbl_per_day.toFixed(1)}` : "—"}{" "}
                <span className="text-[10px] font-normal text-slate-400">Mbbl/d</span>
              </div>
              <div className="text-[10px] font-mono text-slate-500">Seaborne At Risk</div>
            </div>

            <div className="rounded border border-slate-800 bg-[#0B0F19] p-2.5">
              <div className="text-[9px] font-mono uppercase text-slate-400">Stressed Shock</div>
              <div
                id="stress-shock-score"
                className="mt-0.5 text-base font-mono font-bold text-red-400 tabular-nums"
              >
                {result ? formatSigned(result.projected_supply_shock_score, 1) : "—"}
              </div>
              <div className="text-[10px] font-mono text-slate-500">
                {computing ? "Recalculating…" : "Scale -100..+100"}
              </div>
            </div>
          </div>

          {/* 7-Day Forward Stress Trajectory */}
          <div className="flex-1 min-h-[180px] rounded border border-slate-800/90 bg-[#0B0F19] p-2.5">
            <div className="flex items-center justify-between text-[10px] font-mono text-slate-400 mb-1.5">
              <span>7-DAY FORWARD CRUDE TRAJECTORY (BASELINE VS. STRESSED $)</span>
              <div className="flex items-center gap-3">
                <span className="text-emerald-400">━ Stressed Brent</span>
                <span className="text-sky-400">━ Stressed WTI</span>
                <span className="text-slate-500">┄ Baseline</span>
              </div>
            </div>
            <div className="h-[155px]">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={result?.projection_curve || []} margin={{ top: 6, right: 12, left: -12, bottom: 0 }}>
                  <CartesianGrid stroke="#1E293B" strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="label" tick={{ fill: "#94A3B8", fontSize: 10 }} axisLine={false} tickLine={false} />
                  <YAxis
                    domain={["auto", "auto"]}
                    tick={{ fill: "#64748B", fontSize: 10 }}
                    axisLine={false}
                    tickLine={false}
                    tickFormatter={(v) => `$${v}`}
                  />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: "#0D1321",
                      borderColor: "#334155",
                      fontSize: "11px",
                      fontFamily: "monospace",
                    }}
                    formatter={(val) => [`$${Number(val).toFixed(2)}`, ""]}
                  />
                  <Line
                    type="monotone"
                    dataKey="baseline_brent"
                    name="Baseline Brent"
                    stroke="#475569"
                    strokeDasharray="4 4"
                    dot={false}
                    strokeWidth={1.5}
                  />
                  <Line
                    type="monotone"
                    dataKey="stressed_brent"
                    name="Stressed Brent"
                    stroke="#10B981"
                    dot={{ r: 2.5 }}
                    strokeWidth={2.2}
                  />
                  <Line
                    type="monotone"
                    dataKey="stressed_wti"
                    name="Stressed WTI"
                    stroke="#38BDF8"
                    dot={{ r: 2.5 }}
                    strokeWidth={2}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
