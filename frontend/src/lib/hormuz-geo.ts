/**
 * Embedded high-detail GeoJSON features for the Strait of Hormuz (24.0°N–28.0°N, 55.0°E–58.5°E).
 * Guarantees crisp coastline, island, TSS shipping lane, anchorage, and AIS-dark corridor rendering
 * even when external vector/raster basemap tiles are offline or proxy-restricted.
 */

export const HORMUZ_LANDMASS_GEOJSON: GeoJSON.FeatureCollection = {
  type: "FeatureCollection",
  features: [
    {
      type: "Feature",
      properties: { name: "Iran Mainland", kind: "land" },
      geometry: {
        type: "Polygon",
        coordinates: [
          [
            [54.2, 28.6],
            [59.3, 28.6],
            [59.3, 25.4],
            [58.85, 25.55],
            [58.45, 25.63],
            [58.05, 25.66],
            [57.78, 25.64],
            [57.52, 25.88],
            [57.28, 26.25],
            [57.08, 26.64],
            [57.05, 26.98],
            [56.82, 27.14],
            [56.42, 27.19],
            [56.12, 27.14],
            [55.72, 26.92],
            [55.34, 26.66],
            [54.92, 26.55],
            [54.52, 26.74],
            [54.2, 26.95],
            [54.2, 28.6],
          ],
        ],
      },
    },
    {
      type: "Feature",
      properties: { name: "Qeshm Island", kind: "island" },
      geometry: {
        type: "Polygon",
        coordinates: [
          [
            [55.28, 26.58],
            [55.56, 26.67],
            [55.94, 26.86],
            [56.27, 26.97],
            [56.24, 26.86],
            [55.96, 26.68],
            [55.62, 26.56],
            [55.31, 26.52],
            [55.28, 26.58],
          ],
        ],
      },
    },
    {
      type: "Feature",
      properties: { name: "Hormuz Island", kind: "island" },
      geometry: {
        type: "Polygon",
        coordinates: [
          [
            [56.42, 27.09],
            [56.49, 27.10],
            [56.51, 27.04],
            [56.44, 27.03],
            [56.42, 27.09],
          ],
        ],
      },
    },
    {
      type: "Feature",
      properties: { name: "Larak Island", kind: "island" },
      geometry: {
        type: "Polygon",
        coordinates: [
          [
            [56.31, 26.88],
            [56.39, 26.89],
            [56.40, 26.82],
            [56.32, 26.82],
            [56.31, 26.88],
          ],
        ],
      },
    },
    {
      type: "Feature",
      properties: { name: "UAE & Oman / Musandam Peninsula", kind: "land" },
      geometry: {
        type: "Polygon",
        coordinates: [
          [
            [54.2, 23.4],
            [54.2, 24.55],
            [54.78, 24.82],
            [55.12, 25.08],
            [55.38, 25.35],
            [55.65, 25.60],
            [55.94, 25.86],
            [56.12, 26.15],
            [56.25, 26.36],
            [56.42, 26.38],
            [56.46, 26.18],
            [56.38, 25.88],
            [56.35, 25.56],
            [56.36, 25.25],
            [56.38, 24.98],
            [56.52, 24.66],
            [56.78, 24.36],
            [57.28, 24.02],
            [57.95, 23.72],
            [58.85, 23.56],
            [59.3, 23.4],
            [54.2, 23.4],
          ],
        ],
      },
    },
  ],
};

export const HORMUZ_TSS_GEOJSON: GeoJSON.FeatureCollection = {
  type: "FeatureCollection",
  features: [
    {
      type: "Feature",
      properties: { name: "TSS Outbound Lane (Laden Exit)", lane: "outbound" },
      geometry: {
        type: "Polygon",
        coordinates: [
          [
            [55.45, 25.95],
            [56.05, 26.25],
            [56.48, 26.35],
            [56.78, 26.05],
            [57.25, 25.40],
            [57.00, 25.25],
            [56.58, 25.88],
            [56.35, 26.15],
            [55.98, 26.08],
            [55.45, 25.78],
            [55.45, 25.95],
          ],
        ],
      },
    },
    {
      type: "Feature",
      properties: { name: "TSS Inbound Lane (Ballast Entry)", lane: "inbound" },
      geometry: {
        type: "Polygon",
        coordinates: [
          [
            [55.35, 26.28],
            [56.10, 26.62],
            [56.68, 26.62],
            [57.15, 26.20],
            [57.62, 25.65],
            [57.38, 25.48],
            [56.92, 26.02],
            [56.55, 26.42],
            [56.08, 26.42],
            [55.35, 26.10],
            [55.35, 26.28],
          ],
        ],
      },
    },
  ],
};

export const HORMUZ_CORRIDORS_GEOJSON: GeoJSON.FeatureCollection = {
  type: "FeatureCollection",
  features: [
    {
      type: "Feature",
      properties: { name: "AIS-Dark Corridor (25.5°N–27.0°N, 55.8°E–57.0°E)", kind: "dark_corridor" },
      geometry: {
        type: "Polygon",
        coordinates: [
          [
            [55.8, 25.5],
            [57.0, 25.5],
            [57.0, 27.0],
            [55.8, 27.0],
            [55.8, 25.5],
          ],
        ],
      },
    },
    {
      type: "Feature",
      properties: { name: "Strait Monitoring Box", kind: "strait_bbox" },
      geometry: {
        type: "Polygon",
        coordinates: [
          [
            [55.0, 24.0],
            [58.5, 24.0],
            [58.5, 28.0],
            [55.0, 28.0],
            [55.0, 24.0],
          ],
        ],
      },
    },
  ],
};

export const HORMUZ_ANCHORAGES_GEOJSON: GeoJSON.FeatureCollection = {
  type: "FeatureCollection",
  features: [
    {
      type: "Feature",
      properties: { name: "Fujairah Anchorage" },
      geometry: {
        type: "Polygon",
        coordinates: [
          [
            [56.37, 25.0],
            [56.56, 25.0],
            [56.56, 25.28],
            [56.37, 25.28],
            [56.37, 25.0],
          ],
        ],
      },
    },
    {
      type: "Feature",
      properties: { name: "Bandar Abbas Anchorage" },
      geometry: {
        type: "Polygon",
        coordinates: [
          [
            [56.14, 27.04],
            [56.36, 27.04],
            [56.36, 27.16],
            [56.14, 27.16],
            [56.14, 27.04],
          ],
        ],
      },
    },
  ],
};

export const HORMUZ_PORTS_GEOJSON: GeoJSON.FeatureCollection = {
  type: "FeatureCollection",
  features: [
    { type: "Feature", properties: { name: "BANDAR ABBAS" }, geometry: { type: "Point", coordinates: [56.28, 27.18] } },
    { type: "Feature", properties: { name: "FUJAIRAH" }, geometry: { type: "Point", coordinates: [56.33, 25.12] } },
    { type: "Feature", properties: { name: "KHOR FAKKAN" }, geometry: { type: "Point", coordinates: [56.35, 25.34] } },
    { type: "Feature", properties: { name: "MUSANDAM" }, geometry: { type: "Point", coordinates: [56.25, 26.20] } },
    { type: "Feature", properties: { name: "QESHM" }, geometry: { type: "Point", coordinates: [55.85, 26.78] } },
    { type: "Feature", properties: { name: "JASK" }, geometry: { type: "Point", coordinates: [57.77, 25.64] } },
    { type: "Feature", properties: { name: "DUBAI / JEBEL ALI" }, geometry: { type: "Point", coordinates: [55.10, 25.12] } },
    { type: "Feature", properties: { name: "GULF OF OMAN" }, geometry: { type: "Point", coordinates: [57.85, 24.75] } },
    { type: "Feature", properties: { name: "PERSIAN GULF" }, geometry: { type: "Point", coordinates: [55.25, 26.18] } },
  ],
};
