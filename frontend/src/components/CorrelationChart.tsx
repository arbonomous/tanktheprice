"use client";

import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  CandlestickSeries,
  ColorType,
  CrosshairMode,
  HistogramSeries,
  LineSeries,
  createChart,
  createSeriesMarkers,
  type IChartApi,
  type SeriesMarker,
  type Time,
} from "lightweight-charts";
import { AlertCircle, BarChart3, Flame } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { CandlesResponse, OilSymbol } from "@/lib/types";
import { cn, formatSigned } from "@/lib/utils";

interface CorrelationChartProps {
  symbol: OilSymbol;
  onSymbolChange: (symbol: OilSymbol) => void;
  data: CandlesResponse | null;
  loading: boolean;
}

export function CorrelationChart({ symbol, onSymbolChange, data, loading }: CorrelationChartProps) {
  const chartContainerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const [flowMetric, setFlowMetric] = useState<"count" | "mbbl">("count");

  const divergenceDateSet = useMemo(() => {
    const s = new Set<string>();
    for (const z of data?.divergence_zones || []) {
      const start = new Date(z.start_date);
      const end = new Date(z.end_date);
      for (let d = new Date(start); d <= end; d.setUTCDate(d.getUTCDate() + 1)) {
        s.add(d.toISOString().slice(0, 10));
      }
    }
    return s;
  }, [data]);

  useEffect(() => {
    const container = chartContainerRef.current;
    if (!container || !data || data.candles.length === 0) return;

    // Dispose any prior chart cleanly
    if (chartRef.current) {
      chartRef.current.remove();
      chartRef.current = null;
    }

    const chart = createChart(container, {
      width: container.clientWidth,
      height: 320,
      layout: {
        background: { type: ColorType.Solid, color: "#0B0F19" },
        textColor: "#94A3B8",
        fontFamily: "var(--font-jetbrains-mono), ui-monospace, monospace",
        fontSize: 11,
      },
      grid: {
        vertLines: { color: "rgba(30, 41, 59, 0.45)" },
        horzLines: { color: "rgba(30, 41, 59, 0.45)" },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: { color: "#475569", labelBackgroundColor: "#1E293B" },
        horzLine: { color: "#475569", labelBackgroundColor: "#1E293B" },
      },
      rightPriceScale: {
        borderColor: "#1E293B",
        scaleMargins: { top: 0.1, bottom: 0.25 },
      },
      leftPriceScale: {
        visible: true,
        borderColor: "#1E293B",
        scaleMargins: { top: 0.48, bottom: 0.02 },
      },
      timeScale: {
        borderColor: "#1E293B",
        timeVisible: false,
      },
    });
    chartRef.current = chart;

    // Deduplicate & strictly sort candles by YYYY-MM-DD
    const candleByDate = new Map<
      string,
      { time: Time; open: number; high: number; low: number; close: number }
    >();
    for (const c of data.candles) {
      const dayKey = c.timestamp.slice(0, 10);
      candleByDate.set(dayKey, {
        time: dayKey as Time,
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close,
      });
    }
    const sortedCandles = Array.from(candleByDate.entries())
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([, val]) => val);

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: "#10B981",
      downColor: "#EF4444",
      borderUpColor: "#10B981",
      borderDownColor: "#EF4444",
      wickUpColor: "#10B981",
      wickDownColor: "#EF4444",
      priceScaleId: "right",
    });
    candleSeries.setData(sortedCandles);

    // Overlay daily outbound laden tanker count or Mbbl/d on left axis
    const signalByDate = new Map(data.daily_signals.map((s) => [s.date.slice(0, 10), s]));
    const histData: { time: Time; value: number; color: string }[] = [];
    const maData: { time: Time; value: number }[] = [];

    for (const c of sortedCandles) {
      const key = String(c.time);
      const sig = signalByDate.get(key);
      if (!sig) continue;
      const inDiv = divergenceDateSet.has(key);
      histData.push({
        time: c.time,
        value: flowMetric === "count" ? sig.outbound_laden_count : sig.outbound_barrels_mbbl,
        color: inDiv ? "rgba(245, 158, 11, 0.58)" : "rgba(56, 189, 248, 0.28)",
      });
      maData.push({
        time: c.time,
        value: flowMetric === "count" ? sig.outbound_7d_ma : Number((sig.outbound_7d_ma * 1.38).toFixed(2)),
      });
    }

    const flowHist = chart.addSeries(HistogramSeries, {
      priceScaleId: "left",
      priceFormat: { type: "price", precision: flowMetric === "count" ? 0 : 1, minMove: 0.1 },
    });
    flowHist.setData(histData);

    const flowMa = chart.addSeries(LineSeries, {
      priceScaleId: "left",
      color: "#38BDF8",
      lineWidth: 2,
      crosshairMarkerVisible: true,
    });
    flowMa.setData(maData);

    // Highlight Divergence Zones directly on candlestick series via v5 createSeriesMarkers
    const candleKeys = sortedCandles.map((c) => String(c.time));
    const markers: SeriesMarker<Time>[] = [];
    for (const z of data.divergence_zones) {
      const match = candleKeys.find((k) => k >= z.start_date) || candleKeys[candleKeys.length - 1];
      if (!match) continue;
      markers.push({
        time: match as Time,
        position: "aboveBar",
        color: "#F59E0B",
        shape: "arrowDown",
        text: `CHOKE ${z.flow_drop_pct.toFixed(0)}%`,
      });
    }
    if (markers.length > 0) {
      markers.sort((a, b) => String(a.time).localeCompare(String(b.time)));
      createSeriesMarkers(candleSeries, markers);
    }

    chart.timeScale().fitContent();

    const resizeObserver = new ResizeObserver(() => {
      if (container && chartRef.current) {
        chartRef.current.applyOptions({ width: container.clientWidth });
      }
    });
    resizeObserver.observe(container);

    return () => {
      resizeObserver.disconnect();
      chart.remove();
      chartRef.current = null;
    };
  }, [data, flowMetric, divergenceDateSet]);

  return (
    <section
      id="correlation-chart-panel"
      className="terminal-panel rounded-lg overflow-hidden flex flex-col"
    >
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-2 px-4 py-2.5 border-b border-slate-800/90 bg-[#0D1321]/80">
        <div className="flex items-center gap-2">
          <BarChart3 className="h-4 w-4 text-emerald-400" />
          <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-100">
            Dual-Axis Oil Price &amp; Outbound Tanker Flow Overlay
          </h2>
          <Badge variant="neutral" className="hidden sm:inline-flex">
            {data?.source || "yfinance"}
          </Badge>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {/* Brent / WTI Switch */}
          <div className="inline-flex items-center rounded bg-[#0B0F19] border border-slate-800 p-0.5">
            <Button
              id="chart-symbol-brent"
              size="xs"
              variant={symbol === "BZ=F" ? "emerald" : "ghost"}
              onClick={() => onSymbolChange("BZ=F")}
              className="font-mono"
            >
              BRENT (BZ=F)
            </Button>
            <Button
              id="chart-symbol-wti"
              size="xs"
              variant={symbol === "CL=F" ? "default" : "ghost"}
              onClick={() => onSymbolChange("CL=F")}
              className="font-mono"
            >
              WTI (CL=F)
            </Button>
          </div>

          {/* Flow metric toggle */}
          <div className="inline-flex items-center rounded bg-[#0B0F19] border border-slate-800 p-0.5">
            <button
              type="button"
              onClick={() => setFlowMetric("count")}
              className={cn(
                "px-2 py-0.5 text-[10px] font-mono rounded cursor-pointer",
                flowMetric === "count" ? "bg-[#1C2A45] text-slate-100" : "text-slate-400 hover:text-slate-200"
              )}
            >
              TANKERS/D
            </button>
            <button
              type="button"
              onClick={() => setFlowMetric("mbbl")}
              className={cn(
                "px-2 py-0.5 text-[10px] font-mono rounded cursor-pointer",
                flowMetric === "mbbl" ? "bg-[#1C2A45] text-slate-100" : "text-slate-400 hover:text-slate-200"
              )}
            >
              MBBL/D
            </button>
          </div>
        </div>
      </div>

      {/* Legend Strip */}
      <div className="flex flex-wrap items-center justify-between gap-2 px-4 py-1.5 border-b border-slate-800/60 bg-[#0B0F19] text-[10px] font-mono text-slate-400">
        <div className="flex flex-wrap items-center gap-4">
          <span className="inline-flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-xs bg-emerald-400" /> Right Axis: {symbol === "BZ=F" ? "Brent" : "WTI"} OHLC ($)
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-xs bg-sky-400/70" /> Left Axis: Outbound Laden{" "}
            {flowMetric === "count" ? "Tankers" : "Volume (Mbbl)"} + 7d MA
          </span>
          <span className="inline-flex items-center gap-1.5 text-amber-300">
            <span className="h-2 w-2 rounded-xs bg-amber-400" /> Amber Bars: Choke Divergence Zones
          </span>
        </div>
        {loading && <span className="text-sky-400">Updating candles…</span>}
      </div>

      {/* Lightweight Charts Container */}
      <div className="relative bg-[#0B0F19] px-2 pt-2">
        <div ref={chartContainerRef} id="lightweight-chart-container" className="w-full h-[320px]" />
      </div>

      {/* Detected Divergence Zones Footer */}
      <div className="px-4 py-3 border-t border-slate-800/80 bg-[#0D1321]/70">
        <div className="flex items-center gap-1.5 text-[10px] font-mono uppercase tracking-wider text-slate-400 mb-2">
          <Flame className="h-3.5 w-3.5 text-amber-400" />
          Detected Chokepoint Divergence Zones (Tanker Slowdown Preceding Crude Swing)
        </div>
        {data && data.divergence_zones.length > 0 ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
            {data.divergence_zones.map((z, i) => (
              <div
                key={`${z.start_date}-${i}`}
                className="rounded border border-amber-500/25 bg-[#0B0F19] px-3 py-2 flex flex-col gap-1"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="text-[11px] font-mono font-semibold text-amber-300 truncate">{z.label}</span>
                  <span className="text-[10px] font-mono text-slate-500 shrink-0">
                    SHOCK +{z.peak_shock_score.toFixed(0)}
                  </span>
                </div>
                <div className="flex items-center justify-between text-[10px] font-mono text-slate-400">
                  <span>
                    {z.start_date} → {z.end_date}
                  </span>
                  <span className="text-slate-200 tabular-nums">
                    Flow {z.flow_drop_pct.toFixed(0)}% ·{" "}
                    <span className={z.subsequent_brent_move_pct >= 0 ? "text-emerald-400" : "text-red-400"}>
                      BZ {formatSigned(z.subsequent_brent_move_pct, 1, "%")}
                    </span>
                  </span>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-xs font-mono text-slate-500 flex items-center gap-1.5">
            <AlertCircle className="h-3.5 w-3.5" /> No major divergence episodes detected in current lookback window.
          </div>
        )}
      </div>
    </section>
  );
}
