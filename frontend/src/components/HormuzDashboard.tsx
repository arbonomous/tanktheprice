"use client";

import React, { useCallback, useEffect, useState } from "react";
import { AlertCircle } from "lucide-react";
import { AnomalyFeedTable } from "@/components/AnomalyFeedTable";
import { CorrelationChart } from "@/components/CorrelationChart";
import { HormuzMap } from "@/components/HormuzMap";
import { KpiTickerBar } from "@/components/KpiTickerBar";
import { SignalAnalytics } from "@/components/SignalAnalytics";
import { StressTestPanel } from "@/components/StressTestPanel";
import { VesselDrawer } from "@/components/VesselDrawer";
import { hormuzApi } from "@/lib/api";
import type {
  AisGapRecord,
  CandlesResponse,
  DashboardSummary,
  OilSymbol,
  SignalsOverview,
  StressTestResult,
  VesselDetail,
  VesselSnapshot,
} from "@/lib/types";

export function HormuzDashboard() {
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [vessels, setVessels] = useState<VesselSnapshot[]>([]);
  const [aisGaps, setAisGaps] = useState<AisGapRecord[]>([]);
  const [signals, setSignals] = useState<SignalsOverview | null>(null);
  const [symbol, setSymbol] = useState<OilSymbol>("BZ=F");
  const [candles, setCandles] = useState<CandlesResponse | null>(null);
  const [initialStress, setInitialStress] = useState<StressTestResult | null>(null);

  const [selectedVessel, setSelectedVessel] = useState<VesselSnapshot | null>(null);
  const [vesselDetail, setVesselDetail] = useState<VesselDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [focusCoords, setFocusCoords] = useState<{ lat: number; lon: number; ts: number } | null>(null);

  const [loadingCandles, setLoadingCandles] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadAll = useCallback(async (activeSymbol: OilSymbol) => {
    try {
      setError(null);
      const [sumData, vesselData, gapData, sigData, candleData, stressData] = await Promise.all([
        hormuzApi.getSummary(),
        hormuzApi.getVessels(),
        hormuzApi.getAisGaps(),
        hormuzApi.getSignals(),
        hormuzApi.getCandles(activeSymbol, "1d"),
        hormuzApi.runStressTest({
          vlcc_drop_pct: 30,
          ais_spoofing_multiplier: 2.0,
          congestion_surge_pct: 25,
          duration_days: 5,
        }),
      ]);
      setSummary(sumData);
      setVessels(vesselData);
      setAisGaps(gapData);
      setSignals(sigData);
      setCandles(candleData);
      setInitialStress(stressData);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to reach HormuzFlow API");
    }
  }, []);

  useEffect(() => {
    loadAll(symbol);
    // Periodic soft poll every 60s
    const id = setInterval(() => {
      loadAll(symbol);
    }, 60_000);
    return () => clearInterval(id);
  }, [loadAll, symbol]);

  const handleSymbolChange = async (nextSymbol: OilSymbol) => {
    setSymbol(nextSymbol);
    setLoadingCandles(true);
    try {
      const candleData = await hormuzApi.getCandles(nextSymbol, "1d");
      setCandles(candleData);
    } catch {
      // Keep prior candles if transient error
    } finally {
      setLoadingCandles(false);
    }
  };

  const handleSelectVessel = useCallback(async (v: VesselSnapshot) => {
    setSelectedVessel(v);
    setVesselDetail(null);
    setDetailLoading(true);
    try {
      const detail = await hormuzApi.getVesselDetail(v.mmsi);
      setVesselDetail(detail);
    } catch {
      // Historical/synthetic gap vessel may not be in active vessels table
      setVesselDetail(null);
    } finally {
      setDetailLoading(false);
    }
  }, []);

  const handleFocusVessel = useCallback(
    (v: VesselSnapshot) => {
      setFocusCoords({ lat: v.lat, lon: v.lon, ts: Date.now() });
      handleSelectVessel(v);
    },
    [handleSelectVessel]
  );

  const handleRefresh = async () => {
    setRefreshing(true);
    try {
      await hormuzApi.refreshFeeds();
      await loadAll(symbol);
    } finally {
      setRefreshing(false);
    }
  };

  const handleModeChange = async (mode: "auto" | "live" | "simulator") => {
    setRefreshing(true);
    try {
      await hormuzApi.setFeedMode(mode);
      await loadAll(symbol);
    } finally {
      setRefreshing(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#0B0F19] text-[#F1F5F9] flex flex-col">
      <KpiTickerBar
        summary={summary}
        refreshing={refreshing}
        onRefresh={handleRefresh}
        onModeChange={handleModeChange}
      />

      {error && (
        <div className="mx-4 mt-3 rounded-md border border-red-500/40 bg-red-500/10 px-4 py-2.5 text-xs font-mono text-red-200 flex items-center gap-2">
          <AlertCircle className="h-4 w-4 text-red-400 shrink-0" />
          <span>Backend connection issue: {error}. Ensure FastAPI is running on port 8000.</span>
        </div>
      )}

      <main className="flex-1 px-4 py-4 space-y-4 max-w-[1920px] w-full mx-auto">
        {/* Row 1: Strait of Hormuz Live Radar (7 cols) + Quantitative Signal Engine (5 cols) */}
        <div className="grid grid-cols-1 xl:grid-cols-12 gap-4">
          <div className="xl:col-span-7">
            <HormuzMap
              vessels={vessels}
              selectedMmsi={selectedVessel?.mmsi ?? null}
              focusCoords={focusCoords}
              onSelectVessel={handleSelectVessel}
            />
          </div>
          <div className="xl:col-span-5">
            <SignalAnalytics signals={signals} />
          </div>
        </div>

        {/* Row 2: Dual-Axis Oil Price & Outbound Tanker Flow Overlay */}
        <CorrelationChart
          symbol={symbol}
          onSymbolChange={handleSymbolChange}
          data={candles}
          loading={loadingCandles}
        />

        {/* Row 3: Interactive Scenario Stress-Test Simulator */}
        <StressTestPanel initialResult={initialStress} />

        {/* Row 4: Live Chokepoint Anomaly & Dark-Fleet Table */}
        <AnomalyFeedTable aisGaps={aisGaps} vessels={vessels} onFocusVessel={handleFocusVessel} />
      </main>

      <footer className="border-t border-slate-800/80 px-4 py-3 text-[11px] font-mono text-slate-500 flex flex-wrap items-center justify-between gap-2">
        <span>HORMUZFLOW TERMINAL · STRAIT OF HORMUZ MARITIME INTELLIGENCE &amp; OIL SIGNAL ENGINE</span>
        <span>
          MARITIME: {summary?.maritime_source || "loading"} · MARKET: {summary?.market_source || "loading"}
        </span>
      </footer>

      {/* Click-to-Inspect Slide-Over Vessel Drawer */}
      <VesselDrawer
        vessel={selectedVessel}
        detail={vesselDetail}
        loading={detailLoading}
        onClose={() => {
          setSelectedVessel(null);
          setVesselDetail(null);
        }}
      />
    </div>
  );
}
