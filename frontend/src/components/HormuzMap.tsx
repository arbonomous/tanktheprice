"use client";

import React, { useEffect, useMemo, useRef, useState } from "react";
import * as maplibregl from "maplibre-gl";
import { Compass, Layers, LocateFixed, Ship } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  HORMUZ_ANCHORAGES_GEOJSON,
  HORMUZ_CORRIDORS_GEOJSON,
  HORMUZ_LANDMASS_GEOJSON,
  HORMUZ_PORTS_GEOJSON,
  HORMUZ_TSS_GEOJSON,
} from "@/lib/hormuz-geo";
import type { VesselClass, VesselSnapshot, VesselStatus } from "@/lib/types";
import { cn } from "@/lib/utils";

interface HormuzMapProps {
  vessels: VesselSnapshot[];
  selectedMmsi: string | null;
  focusCoords: { lat: number; lon: number; ts: number } | null;
  onSelectVessel: (vessel: VesselSnapshot) => void;
}

const STATUS_META: Record<
  VesselStatus,
  { label: string; color: string; stroke: string; dotClass: string }
> = {
  outbound_laden: {
    label: "Outbound Laden",
    color: "#10B981",
    stroke: "#064E3B",
    dotClass: "bg-emerald-400",
  },
  inbound_ballast: {
    label: "Inbound Ballast",
    color: "#38BDF8",
    stroke: "#0C4A6E",
    dotClass: "bg-sky-400",
  },
  loitering: {
    label: "Loitering / Queue",
    color: "#F59E0B",
    stroke: "#78350F",
    dotClass: "bg-amber-400",
  },
  ais_gap: {
    label: "AIS Gap / Dark",
    color: "#EF4444",
    stroke: "#7F1D1D",
    dotClass: "bg-red-500",
  },
};

export function HormuzMap({ vessels, selectedMmsi, focusCoords, onSelectVessel }: HormuzMapProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const markersRef = useRef<Map<string, maplibregl.Marker>>(new Map());
  const portMarkersRef = useRef<maplibregl.Marker[]>([]);

  const [statusFilter, setStatusFilter] = useState<VesselStatus | "all">("all");
  const [classFilter, setClassFilter] = useState<VesselClass | "all">("all");
  const [showTss, setShowTss] = useState(true);
  const [showDarkCorridor, setShowDarkCorridor] = useState(true);
  const [showAnchorages, setShowAnchorages] = useState(true);
  const [mapReady, setMapReady] = useState(false);

  const filteredVessels = useMemo(() => {
    return vessels.filter((v) => {
      if (statusFilter !== "all" && v.status !== statusFilter) return false;
      if (classFilter !== "all" && v.vessel_class !== classFilter) return false;
      return true;
    });
  }, [vessels, statusFilter, classFilter]);

  const countsByStatus = useMemo(() => {
    const counts: Record<VesselStatus, number> = {
      outbound_laden: 0,
      inbound_ballast: 0,
      loitering: 0,
      ais_gap: 0,
    };
    for (const v of vessels) {
      counts[v.status] = (counts[v.status] || 0) + 1;
    }
    return counts;
  }, [vessels]);

  // Initialize MapLibre GL JS with deterministic zero-dependency dark maritime chart style
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    maplibregl.setWorkerUrl("/maplibre-gl-worker.js");

    const styleSpec: maplibregl.StyleSpecification = {
      version: 8,
      name: "HormuzFlow Dark Maritime",
      sources: {
        landmass: { type: "geojson", data: HORMUZ_LANDMASS_GEOJSON },
        tss: { type: "geojson", data: HORMUZ_TSS_GEOJSON },
        corridors: { type: "geojson", data: HORMUZ_CORRIDORS_GEOJSON },
        anchorages: { type: "geojson", data: HORMUZ_ANCHORAGES_GEOJSON },
      },
      layers: [
        {
          id: "ocean-bg",
          type: "background",
          paint: { "background-color": "#070D19" },
        },
        {
          id: "strait-bbox-outline",
          type: "line",
          source: "corridors",
          filter: ["==", ["get", "kind"], "strait_bbox"],
          paint: {
            "line-color": "#1E3A5F",
            "line-width": 1,
            "line-dasharray": [4, 4],
          },
        },
        {
          id: "tss-outbound-fill",
          type: "fill",
          source: "tss",
          filter: ["==", ["get", "lane"], "outbound"],
          paint: {
            "fill-color": "#10B981",
            "fill-opacity": 0.08,
          },
        },
        {
          id: "tss-outbound-line",
          type: "line",
          source: "tss",
          filter: ["==", ["get", "lane"], "outbound"],
          paint: {
            "line-color": "#10B981",
            "line-opacity": 0.42,
            "line-width": 1.25,
          },
        },
        {
          id: "tss-inbound-fill",
          type: "fill",
          source: "tss",
          filter: ["==", ["get", "lane"], "inbound"],
          paint: {
            "fill-color": "#38BDF8",
            "fill-opacity": 0.07,
          },
        },
        {
          id: "tss-inbound-line",
          type: "line",
          source: "tss",
          filter: ["==", ["get", "lane"], "inbound"],
          paint: {
            "line-color": "#38BDF8",
            "line-opacity": 0.42,
            "line-width": 1.25,
          },
        },
        {
          id: "anchorages-fill",
          type: "fill",
          source: "anchorages",
          paint: {
            "fill-color": "#F59E0B",
            "fill-opacity": 0.1,
          },
        },
        {
          id: "anchorages-line",
          type: "line",
          source: "anchorages",
          paint: {
            "line-color": "#F59E0B",
            "line-opacity": 0.55,
            "line-width": 1,
            "line-dasharray": [2, 2],
          },
        },
        {
          id: "dark-corridor-fill",
          type: "fill",
          source: "corridors",
          filter: ["==", ["get", "kind"], "dark_corridor"],
          paint: {
            "fill-color": "#EF4444",
            "fill-opacity": 0.06,
          },
        },
        {
          id: "dark-corridor-line",
          type: "line",
          source: "corridors",
          filter: ["==", ["get", "kind"], "dark_corridor"],
          paint: {
            "line-color": "#EF4444",
            "line-opacity": 0.55,
            "line-width": 1.4,
            "line-dasharray": [4, 3],
          },
        },
        {
          id: "landmass-fill",
          type: "fill",
          source: "landmass",
          paint: {
            "fill-color": "#131C2E",
            "fill-opacity": 0.96,
          },
        },
        {
          id: "landmass-coastline",
          type: "line",
          source: "landmass",
          paint: {
            "line-color": "#314668",
            "line-width": 1.3,
          },
        },
      ],
    };

    const map = new maplibregl.Map({
      container: containerRef.current,
      style: styleSpec,
      center: [56.5, 26.05],
      zoom: 6.95,
      minZoom: 5.5,
      maxZoom: 12,
      attributionControl: false,
    });

    map.addControl(new maplibregl.NavigationControl({ showCompass: true }), "top-right");

    map.on("load", () => {
      setMapReady(true);

      // Render port / chokepoint labels as lightweight non-interactive markers (zero remote glyph fetch)
      for (const feat of HORMUZ_PORTS_GEOJSON.features) {
        if (feat.geometry.type !== "Point") continue;
        const [lon, lat] = feat.geometry.coordinates;
        const el = document.createElement("div");
        el.className =
          "pointer-events-none select-none font-mono text-[9px] tracking-[0.14em] text-slate-400/80 bg-[#070D19]/65 px-1.5 py-0.5 rounded border border-slate-800/70 whitespace-nowrap";
        el.textContent = String(feat.properties?.name || "");
        const m = new maplibregl.Marker({ element: el, anchor: "center" }).setLngLat([lon, lat]).addTo(map);
        portMarkersRef.current.push(m);
      }
    });

    mapRef.current = map;

    return () => {
      portMarkersRef.current.forEach((m) => m.remove());
      portMarkersRef.current = [];
      markersRef.current.forEach((m) => m.remove());
      markersRef.current.clear();
      map.remove();
      mapRef.current = null;
    };
  }, []);

  // Toggle overlay visibility
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    const setVis = (ids: string[], visible: boolean) => {
      for (const id of ids) {
        if (map.getLayer(id)) {
          map.setLayoutProperty(id, "visibility", visible ? "visible" : "none");
        }
      }
    };
    setVis(["tss-outbound-fill", "tss-outbound-line", "tss-inbound-fill", "tss-inbound-line"], showTss);
    setVis(["dark-corridor-fill", "dark-corridor-line"], showDarkCorridor);
    setVis(["anchorages-fill", "anchorages-line"], showAnchorages);
  }, [mapReady, showTss, showDarkCorridor, showAnchorages]);

  // Sync vessel markers onto MapLibre canvas
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;

    markersRef.current.forEach((m) => m.remove());
    markersRef.current.clear();

    for (const v of filteredVessels) {
      const meta = STATUS_META[v.status];
      const isSelected = selectedMmsi === v.mmsi;
      const size = v.vessel_class === "VLCC" ? 18 : v.vessel_class === "Suezmax" ? 15 : 13;

      // Outer marker element MUST NOT use CSS transform/scale or position:relative
      // because MapLibre controls position:absolute & transform:translate(...) on it.
      const btn = document.createElement("button");
      btn.type = "button";
      btn.dataset.mmsi = v.mmsi;
      btn.dataset.status = v.status;
      btn.dataset.vesselClass = v.vessel_class;
      btn.setAttribute("aria-label", `${v.name} (${v.vessel_class}) — ${meta.label}`);
      btn.title = `${v.name} · ${v.vessel_class} · ${v.speed_knots} kn · Draft ${v.draft_m}m · ${v.destination}`;
      btn.className = cn(
        "vessel-marker group flex items-center justify-center rounded-full cursor-pointer focus:outline-none bg-transparent border-0 p-0",
        isSelected ? "z-20" : "z-10"
      );
      btn.style.width = `${size + 10}px`;
      btn.style.height = `${size + 10}px`;

      const ringHtml = isSelected
        ? `<span style="position:absolute;inset:-3px;border-radius:9999px;border:2px solid #F8FAFC;box-shadow:0 0 10px ${meta.color};"></span>`
        : v.is_sanctioned
          ? `<span style="position:absolute;inset:-2px;border-radius:9999px;border:1.5px dashed #EF4444;"></span>`
          : "";

      btn.innerHTML = `
        <span class="relative flex items-center justify-center w-full h-full transition-transform ${
          isSelected ? "scale-125" : "group-hover:scale-125"
        }">
          ${ringHtml}
          <svg width="${size}" height="${size}" viewBox="0 0 24 24" style="transform:rotate(${v.heading}deg);filter:drop-shadow(0 1px 3px rgba(0,0,0,0.9));">
            <path d="M12 2L19 20L12 16.5L5 20L12 2Z" fill="${meta.color}" stroke="${meta.stroke}" stroke-width="1.5" stroke-linejoin="round" />
          </svg>
        </span>
      `;

      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        onSelectVessel(v);
      });

      const marker = new maplibregl.Marker({ element: btn, anchor: "center" })
        .setLngLat([v.lon, v.lat])
        .addTo(map);
      markersRef.current.set(v.mmsi, marker);
    }
  }, [filteredVessels, mapReady, selectedMmsi, onSelectVessel]);

  // Fly to focused vessel when clicked from Anomaly Table
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !focusCoords) return;
    map.flyTo({ center: [focusCoords.lon, focusCoords.lat], zoom: 8.6, duration: 700 });
  }, [focusCoords]);

  const resetViewport = () => {
    mapRef.current?.flyTo({ center: [56.5, 26.05], zoom: 6.95, duration: 600 });
  };

  return (
    <section
      id="hormuz-map-panel"
      className="terminal-panel rounded-lg overflow-hidden flex flex-col h-[520px] xl:h-[560px]"
    >
      {/* Map Header & Filters */}
      <div className="flex flex-wrap items-center justify-between gap-2 px-3.5 py-2.5 border-b border-slate-800/90 bg-[#0D1321]/80">
        <div className="flex items-center gap-2">
          <Compass className="h-4 w-4 text-sky-400" />
          <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-100">
            Strait of Hormuz Live Tanker Radar
          </h2>
          <Badge variant="sky" className="tabular-nums">
            {filteredVessels.length} / {vessels.length} VESSELS
          </Badge>
        </div>

        <div className="flex flex-wrap items-center gap-1.5">
          {/* Vessel Class Filter */}
          <div className="inline-flex items-center rounded bg-[#0B0F19] border border-slate-800 p-0.5">
            {(["all", "VLCC", "Suezmax", "Aframax"] as const).map((cls) => (
              <button
                key={cls}
                type="button"
                onClick={() => setClassFilter(cls)}
                className={cn(
                  "px-2 py-0.5 text-[10px] font-mono uppercase rounded transition-colors cursor-pointer",
                  classFilter === cls
                    ? "bg-[#1C2A45] text-slate-100"
                    : "text-slate-400 hover:text-slate-200"
                )}
              >
                {cls === "all" ? "ALL CLASS" : cls}
              </button>
            ))}
          </div>

          <Button
            size="xs"
            variant={showTss ? "emerald" : "ghost"}
            onClick={() => setShowTss((s) => !s)}
            className="font-mono text-[10px]"
          >
            <Layers className="h-3 w-3" />
            TSS
          </Button>
          <Button
            size="xs"
            variant={showDarkCorridor ? "danger" : "ghost"}
            onClick={() => setShowDarkCorridor((s) => !s)}
            className="font-mono text-[10px]"
          >
            DARK ZONE
          </Button>
          <Button
            size="xs"
            variant={showAnchorages ? "secondary" : "ghost"}
            onClick={() => setShowAnchorages((s) => !s)}
            className="font-mono text-[10px]"
          >
            ANCHORAGES
          </Button>
          <Button
            size="xs"
            variant="ghost"
            onClick={resetViewport}
            title="Reset Strait of Hormuz viewport"
          >
            <LocateFixed className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>

      {/* MapLibre Canvas */}
      <div className="relative flex-1 min-h-0 bg-[#070D19]">
        <div ref={containerRef} id="hormuz-map-canvas" className="w-full h-full" />

        {/* Interactive Legend & Status Filter Overlay */}
        <div className="absolute bottom-3 left-3 z-10 flex flex-wrap items-center gap-1.5 rounded-md border border-slate-800/90 bg-[#0B0F19]/90 backdrop-blur-sm px-2.5 py-1.5 shadow-xl">
          <button
            type="button"
            onClick={() => setStatusFilter("all")}
            className={cn(
              "inline-flex items-center gap-1.5 rounded px-2 py-0.5 text-[10px] font-mono transition-colors cursor-pointer",
              statusFilter === "all"
                ? "bg-slate-700/80 text-white"
                : "text-slate-400 hover:text-slate-200"
            )}
          >
            <Ship className="h-3 w-3" />
            ALL ({vessels.length})
          </button>

          {(Object.entries(STATUS_META) as [VesselStatus, (typeof STATUS_META)[VesselStatus]][]).map(
            ([key, meta]) => (
              <button
                key={key}
                type="button"
                onClick={() => setStatusFilter(statusFilter === key ? "all" : key)}
                className={cn(
                  "inline-flex items-center gap-1.5 rounded px-2 py-0.5 text-[10px] font-mono transition-colors cursor-pointer",
                  statusFilter === key
                    ? "bg-slate-700/90 text-white"
                    : "text-slate-300 hover:bg-slate-800/70"
                )}
              >
                <span className={cn("h-2 w-2 rounded-full", meta.dotClass)} />
                <span>{meta.label}</span>
                <span className="text-slate-500 tabular-nums">({countsByStatus[key]})</span>
              </button>
            )
          )}
        </div>

        {/* Click Hint */}
        <div className="absolute top-3 left-3 z-10 pointer-events-none rounded border border-slate-800/80 bg-[#0B0F19]/85 px-2 py-1 text-[10px] font-mono text-slate-400">
          CLICK ANY TANKER TO INSPECT TELEMETRY · DASHED RED = AIS-DARK CORRIDOR
        </div>
      </div>
    </section>
  );
}
