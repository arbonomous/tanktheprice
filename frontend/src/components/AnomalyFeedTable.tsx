"use client";

import React from "react";
import { AlertTriangle, Clock, Crosshair, Radio, ShieldAlert } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { AisGapRecord, VesselSnapshot } from "@/lib/types";
import { formatCoord, formatUtcTime } from "@/lib/utils";

interface AnomalyFeedTableProps {
  aisGaps: AisGapRecord[];
  vessels: VesselSnapshot[];
  onFocusVessel: (vessel: VesselSnapshot) => void;
}

export function AnomalyFeedTable({ aisGaps, vessels, onFocusVessel }: AnomalyFeedTableProps) {
  const vesselByMmsi = new Map(vessels.map((v) => [v.mmsi, v]));
  const loiteringVessels = vessels.filter((v) => v.status === "loitering");
  const darkVessels = vessels.filter((v) => v.status === "ais_gap");

  const handleGapRowClick = (gap: AisGapRecord) => {
    const existing = vesselByMmsi.get(gap.vessel_mmsi);
    if (existing) {
      onFocusVessel(existing);
      return;
    }
    // Synthesize inspectable snapshot for historical resolved gap
    onFocusVessel({
      mmsi: gap.vessel_mmsi,
      imo: `IMO${gap.vessel_mmsi.slice(0, 7)}`,
      name: gap.vessel_name,
      vessel_class: gap.vessel_class,
      flag: gap.is_sanctioned ? "IR" : "PA",
      lat: gap.last_lat,
      lon: gap.last_lon,
      speed_knots: 0.0,
      heading: 120.0,
      draft_m: 16.4,
      destination: "UNKNOWN / DARK GAP",
      status: "ais_gap",
      is_sanctioned: gap.is_sanctioned,
      dwt: gap.vessel_class === "VLCC" ? 305000 : 155000,
      barrel_capacity: gap.vessel_class === "VLCC" ? 2.0 : 1.0,
      ais_gap_hours: gap.duration_hours,
      last_seen: gap.start_time,
      source: gap.source,
    });
  };

  return (
    <section id="anomaly-feed-panel" className="terminal-panel rounded-lg overflow-hidden">
      <Tabs defaultValue="dark">
        <div className="flex flex-wrap items-center justify-between gap-2 px-4 py-2.5 border-b border-slate-800/90 bg-[#0D1321]/80">
          <div className="flex items-center gap-2">
            <Radio className="h-4 w-4 text-red-400" />
            <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-100">
              Live Chokepoint Anomaly &amp; Dark-Fleet Log
            </h2>
          </div>

          <TabsList>
            <TabsTrigger value="dark">AIS-DARK EVENTS ({aisGaps.length})</TabsTrigger>
            <TabsTrigger value="loitering">LOITERING / QUEUE ({loiteringVessels.length})</TabsTrigger>
          </TabsList>
        </div>

        <TabsContent value="dark" className="overflow-x-auto max-h-[300px] overflow-y-auto">
          <table className="w-full text-left border-collapse">
            <thead className="sticky top-0 bg-[#0D1321] text-[10px] font-mono uppercase text-slate-400 border-b border-slate-800">
              <tr>
                <th className="py-2 px-3">Vessel / MMSI</th>
                <th className="py-2 px-3">Class</th>
                <th className="py-2 px-3">Severity</th>
                <th className="py-2 px-3">Silence Duration</th>
                <th className="py-2 px-3">Last Known Position</th>
                <th className="py-2 px-3">Status</th>
                <th className="py-2 px-3 text-right">Inspect</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/70 text-xs">
              {aisGaps.slice(0, 16).map((g, idx) => (
                <tr
                  key={`${g.vessel_mmsi}-${idx}`}
                  onClick={() => handleGapRowClick(g)}
                  className="hover:bg-[#162033]/80 transition-colors cursor-pointer"
                >
                  <td className="py-2 px-3">
                    <div className="font-mono font-semibold text-slate-100 flex items-center gap-1.5">
                      <span>{g.vessel_name}</span>
                      {g.is_sanctioned && (
                        <ShieldAlert className="h-3.5 w-3.5 text-red-400 shrink-0" aria-label="Sanctioned" />
                      )}
                    </div>
                    <div className="text-[10px] font-mono text-slate-500">{g.vessel_mmsi}</div>
                  </td>
                  <td className="py-2 px-3 font-mono text-slate-300">{g.vessel_class}</td>
                  <td className="py-2 px-3">
                    <Badge variant={g.severity === "CRITICAL" ? "red" : g.severity === "HIGH" ? "amber" : "neutral"}>
                      {g.severity}
                    </Badge>
                  </td>
                  <td className="py-2 px-3 font-mono text-red-300 tabular-nums">
                    <span className="inline-flex items-center gap-1">
                      <Clock className="h-3 w-3 text-slate-500" />
                      {g.duration_hours.toFixed(1)}h
                    </span>
                  </td>
                  <td className="py-2 px-3 font-mono text-slate-300 tabular-nums">
                    {formatCoord(g.last_lat, g.last_lon)}
                  </td>
                  <td className="py-2 px-3 font-mono text-[11px]">
                    {g.end_time === null ? (
                      <span className="text-red-400">ACTIVE DARK</span>
                    ) : (
                      <span className="text-slate-400">REAPPEARED · {formatUtcTime(g.end_time).slice(5, 16)}</span>
                    )}
                  </td>
                  <td className="py-2 px-3 text-right">
                    <span className="inline-flex items-center gap-1 text-[10px] font-mono text-sky-400">
                      <Crosshair className="h-3 w-3" /> LOCATE
                    </span>
                  </td>
                </tr>
              ))}
              {darkVessels.length === 0 && aisGaps.length === 0 && (
                <tr>
                  <td colSpan={7} className="py-6 text-center text-xs font-mono text-slate-500">
                    No active AIS-dark corridor anomalies.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </TabsContent>

        <TabsContent value="loitering" className="overflow-x-auto max-h-[300px] overflow-y-auto">
          <table className="w-full text-left border-collapse">
            <thead className="sticky top-0 bg-[#0D1321] text-[10px] font-mono uppercase text-slate-400 border-b border-slate-800">
              <tr>
                <th className="py-2 px-3">Vessel / MMSI</th>
                <th className="py-2 px-3">Class</th>
                <th className="py-2 px-3">Speed</th>
                <th className="py-2 px-3">Draft</th>
                <th className="py-2 px-3">Destination / Queue</th>
                <th className="py-2 px-3">Position</th>
                <th className="py-2 px-3 text-right">Inspect</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/70 text-xs">
              {loiteringVessels.map((v) => (
                <tr
                  key={v.mmsi}
                  onClick={() => onFocusVessel(v)}
                  className="hover:bg-[#162033]/80 transition-colors cursor-pointer"
                >
                  <td className="py-2 px-3">
                    <div className="font-mono font-semibold text-slate-100 flex items-center gap-1.5">
                      <AlertTriangle className="h-3 w-3 text-amber-400 shrink-0" />
                      <span>{v.name}</span>
                    </div>
                    <div className="text-[10px] font-mono text-slate-500">{v.mmsi} · {v.imo}</div>
                  </td>
                  <td className="py-2 px-3 font-mono text-slate-300">{v.vessel_class}</td>
                  <td className="py-2 px-3 font-mono text-amber-300 tabular-nums">{v.speed_knots.toFixed(1)} kn</td>
                  <td className="py-2 px-3 font-mono text-slate-300 tabular-nums">{v.draft_m.toFixed(1)} m</td>
                  <td className="py-2 px-3 font-mono text-slate-300">{v.destination}</td>
                  <td className="py-2 px-3 font-mono text-slate-400 tabular-nums">{formatCoord(v.lat, v.lon)}</td>
                  <td className="py-2 px-3 text-right">
                    <span className="inline-flex items-center gap-1 text-[10px] font-mono text-sky-400">
                      <Crosshair className="h-3 w-3" /> LOCATE
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </TabsContent>
      </Tabs>
    </section>
  );
}
