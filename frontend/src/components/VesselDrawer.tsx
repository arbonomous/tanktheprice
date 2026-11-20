"use client";

import React from "react";
import {
  AlertTriangle,
  Compass,
  Gauge,
  MapPin,
  Navigation,
  Radio,
  ShieldAlert,
  Ship,
  X,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { VesselDetail, VesselSnapshot } from "@/lib/types";
import { formatCoord, formatUtcTime } from "@/lib/utils";

interface VesselDrawerProps {
  vessel: VesselSnapshot | null;
  detail: VesselDetail | null;
  loading: boolean;
  onClose: () => void;
}

export function VesselDrawer({ vessel, detail, loading, onClose }: VesselDrawerProps) {
  if (!vessel) return null;

  const statusBadgeVariant =
    vessel.status === "outbound_laden"
      ? "emerald"
      : vessel.status === "inbound_ballast"
        ? "sky"
        : vessel.status === "loitering"
          ? "amber"
          : "red";

  const statusLabel = {
    outbound_laden: "OUTBOUND LADEN",
    inbound_ballast: "INBOUND BALLAST",
    loitering: "LOITERING / QUEUED",
    ais_gap: "AIS GAP / DARK SHIP",
  }[vessel.status];

  return (
    <aside
      id="vessel-drawer"
      aria-label="Vessel Inspection Drawer"
      className="fixed inset-y-0 right-0 z-50 w-full max-w-md border-l border-slate-700/80 bg-[#0D1321]/98 backdrop-blur-xl shadow-2xl flex flex-col"
    >
      {/* Drawer Header */}
      <div className="flex items-start justify-between gap-3 px-5 py-4 border-b border-slate-800 bg-[#101726]">
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <Ship className="h-4 w-4 text-sky-400 shrink-0" />
            <h2 id="vessel-drawer-name" className="text-base font-bold tracking-wide text-slate-100 truncate">
              {vessel.name}
            </h2>
          </div>
          <div className="mt-1.5 flex items-center gap-1.5 flex-wrap">
            <Badge variant={statusBadgeVariant}>{statusLabel}</Badge>
            <Badge variant="neutral">{vessel.vessel_class}</Badge>
            <Badge variant="neutral">FLAG: {vessel.flag}</Badge>
            {vessel.is_sanctioned && (
              <Badge variant="red">
                <ShieldAlert className="h-3 w-3" /> SANCTIONED FLAG
              </Badge>
            )}
          </div>
        </div>
        <Button id="vessel-drawer-close" variant="ghost" size="icon" onClick={onClose} aria-label="Close vessel drawer">
          <X className="h-4 w-4" />
        </Button>
      </div>

      {/* Drawer Content */}
      <div className="flex-1 overflow-y-auto p-5 space-y-5">
        {/* Sanctioned or AIS-Dark Alert */}
        {(vessel.is_sanctioned || vessel.status === "ais_gap") && (
          <div className="rounded-md border border-red-500/35 bg-red-500/10 p-3 flex items-start gap-2.5">
            <AlertTriangle className="h-4 w-4 text-red-400 shrink-0 mt-0.5" />
            <div className="text-xs text-red-200 leading-relaxed">
              <p className="font-semibold uppercase tracking-wider text-red-300">
                Dark-Fleet / Compliance Alert
              </p>
              <p className="mt-0.5 text-red-200/85">
                {vessel.status === "ais_gap"
                  ? `AIS transponder silent for ${vessel.ais_gap_hours.toFixed(1)}h inside Strait of Hormuz corridor.`
                  : "Vessel appears on active sanctioned tanker watchlist."}
              </p>
            </div>
          </div>
        )}

        {/* Primary Identifiers */}
        <div className="grid grid-cols-2 gap-2.5">
          <div className="rounded border border-slate-800 bg-[#0B0F19] p-3">
            <div className="text-[10px] font-mono uppercase text-slate-500">MMSI</div>
            <div id="vessel-drawer-mmsi" className="mt-0.5 text-sm font-mono font-semibold text-slate-100 tabular-nums">
              {vessel.mmsi}
            </div>
          </div>
          <div className="rounded border border-slate-800 bg-[#0B0F19] p-3">
            <div className="text-[10px] font-mono uppercase text-slate-500">IMO NUMBER</div>
            <div id="vessel-drawer-imo" className="mt-0.5 text-sm font-mono font-semibold text-slate-100 tabular-nums">
              {vessel.imo}
            </div>
          </div>
          <div className="rounded border border-slate-800 bg-[#0B0F19] p-3">
            <div className="text-[10px] font-mono uppercase text-slate-500">VESSEL CLASS / DWT</div>
            <div className="mt-0.5 text-sm font-mono font-semibold text-slate-100 tabular-nums">
              {vessel.vessel_class} · {(vessel.dwt / 1000).toFixed(0)}k DWT
            </div>
          </div>
          <div className="rounded border border-slate-800 bg-[#0B0F19] p-3">
            <div className="text-[10px] font-mono uppercase text-slate-500">EST. CARGO CAPACITY</div>
            <div className="mt-0.5 text-sm font-mono font-semibold text-emerald-300 tabular-nums">
              {vessel.barrel_capacity.toFixed(2)} Mbbl
            </div>
          </div>
        </div>

        {/* Live Telemetry Grid */}
        <div>
          <h3 className="text-[11px] font-mono uppercase tracking-wider text-slate-400 mb-2">
            Navigation &amp; Voyage Telemetry
          </h3>
          <div className="grid grid-cols-3 gap-2">
            <div className="rounded border border-slate-800 bg-[#101726] p-2.5">
              <div className="flex items-center gap-1 text-[10px] font-mono text-slate-400">
                <Gauge className="h-3 w-3 text-sky-400" /> SPEED
              </div>
              <div className="mt-1 text-base font-mono font-semibold text-slate-100 tabular-nums">
                {vessel.speed_knots.toFixed(1)} <span className="text-[10px] text-slate-400">kn</span>
              </div>
            </div>
            <div className="rounded border border-slate-800 bg-[#101726] p-2.5">
              <div className="flex items-center gap-1 text-[10px] font-mono text-slate-400">
                <Compass className="h-3 w-3 text-emerald-400" /> HEADING
              </div>
              <div className="mt-1 text-base font-mono font-semibold text-slate-100 tabular-nums">
                {vessel.heading.toFixed(0)}°
              </div>
            </div>
            <div className="rounded border border-slate-800 bg-[#101726] p-2.5">
              <div className="flex items-center gap-1 text-[10px] font-mono text-slate-400">
                <Navigation className="h-3 w-3 text-amber-400" /> DRAFT
              </div>
              <div className="mt-1 text-base font-mono font-semibold text-slate-100 tabular-nums">
                {vessel.draft_m.toFixed(1)} <span className="text-[10px] text-slate-400">m</span>
              </div>
            </div>
          </div>

          <div className="mt-2.5 rounded border border-slate-800 bg-[#101726] p-3 space-y-2 text-xs">
            <div className="flex items-center justify-between">
              <span className="text-slate-400 font-mono text-[11px]">DESTINATION</span>
              <span className="font-mono font-semibold text-slate-100">{vessel.destination}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-slate-400 font-mono text-[11px] inline-flex items-center gap-1">
                <MapPin className="h-3 w-3 text-slate-500" /> POSITION
              </span>
              <span className="font-mono text-slate-200 tabular-nums">
                {formatCoord(vessel.lat, vessel.lon)}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-slate-400 font-mono text-[11px]">LAST AIS PING</span>
              <span className="font-mono text-slate-300 tabular-nums">{formatUtcTime(vessel.last_seen)}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-slate-400 font-mono text-[11px]">FEED SOURCE</span>
              <span className="font-mono text-sky-300">{vessel.source}</span>
            </div>
          </div>
        </div>

        {/* Geospatial Zone Diagnostics */}
        <div>
          <h3 className="text-[11px] font-mono uppercase tracking-wider text-slate-400 mb-2">
            Chokepoint Corridor Diagnostics
          </h3>
          {loading ? (
            <div className="text-xs font-mono text-slate-500 py-2">Loading corridor diagnostics…</div>
          ) : (
            <div className="flex flex-wrap gap-1.5">
              <Badge variant={detail?.in_dark_corridor ? "red" : "neutral"}>
                {detail?.in_dark_corridor ? "INSIDE DARK CORRIDOR" : "OUTSIDE DARK CORRIDOR"}
              </Badge>
              <Badge variant={detail?.in_tss_lane ? "sky" : "neutral"}>
                {detail?.in_tss_lane ? "INSIDE TSS LANE" : "OUTSIDE TSS"}
              </Badge>
              <Badge variant={detail?.is_congestion_loitering ? "amber" : "neutral"}>
                {detail?.is_congestion_loitering ? "LOITERING ANOMALY" : "NORMAL TRANSIT SPEED"}
              </Badge>
            </div>
          )}
        </div>

        {/* Vessel AIS Gap History */}
        <div>
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-[11px] font-mono uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
              <Radio className="h-3.5 w-3.5 text-red-400" /> AIS Gap Event History
            </h3>
            <span className="text-[10px] font-mono text-slate-500">
              {detail?.ais_gap_history.length ?? 0} EVENTS
            </span>
          </div>
          {detail && detail.ais_gap_history.length > 0 ? (
            <div className="space-y-2">
              {detail.ais_gap_history.map((g, idx) => (
                <div
                  key={`${g.vessel_mmsi}-${idx}`}
                  className="rounded border border-red-500/25 bg-[#0B0F19] p-2.5 text-xs space-y-1"
                >
                  <div className="flex items-center justify-between">
                    <Badge variant={g.severity === "CRITICAL" ? "red" : "amber"}>{g.severity}</Badge>
                    <span className="font-mono text-red-300 font-semibold tabular-nums">
                      {g.duration_hours.toFixed(1)}h SILENT
                    </span>
                  </div>
                  <div className="text-[11px] font-mono text-slate-400">
                    Start: {formatUtcTime(g.start_time)}
                  </div>
                  <div className="text-[11px] font-mono text-slate-400">
                    Last Known: {formatCoord(g.last_lat, g.last_lon)}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="rounded border border-slate-800 bg-[#0B0F19] px-3 py-2.5 text-xs text-slate-500 font-mono">
              No historical AIS blackout events recorded for this vessel.
            </div>
          )}
        </div>
      </div>
    </aside>
  );
}
