import type {
  AisGapRecord,
  CandlesResponse,
  DashboardSummary,
  OilSymbol,
  SignalsOverview,
  StressTestPayload,
  StressTestResult,
  VesselDetail,
  VesselSnapshot,
} from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`API ${res.status}: ${path}`);
  }
  return res.json() as Promise<T>;
}

export const hormuzApi = {
  getSummary: () => apiFetch<DashboardSummary>("/api/dashboard/summary"),
  getVessels: () => apiFetch<VesselSnapshot[]>("/api/vessels"),
  getVesselDetail: (mmsi: string) => apiFetch<VesselDetail>(`/api/vessels/${encodeURIComponent(mmsi)}`),
  getAisGaps: () => apiFetch<AisGapRecord[]>("/api/ais-gaps"),
  getCandles: (symbol: OilSymbol, interval: "1d" | "1h" = "1d") =>
    apiFetch<CandlesResponse>(`/api/market/candles?symbol=${encodeURIComponent(symbol)}&interval=${interval}`),
  getSignals: () => apiFetch<SignalsOverview>("/api/signals/overview"),
  runStressTest: (payload: StressTestPayload) =>
    apiFetch<StressTestResult>("/api/simulation/stress-test", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  refreshFeeds: () => apiFetch<DashboardSummary>("/api/adapters/refresh", { method: "POST" }),
  setFeedMode: (feed_mode: "auto" | "live" | "simulator") =>
    apiFetch<DashboardSummary>("/api/adapters/mode", {
      method: "POST",
      body: JSON.stringify({ feed_mode }),
    }),
};
