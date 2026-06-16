import { useEffect, useRef, useState } from "react";
import L from "leaflet";

// Leaflet base layers. Esri World Imagery needs no token (spec §8).
const SAT_URL =
  "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}";
const SAT_ATTR = "Tiles © Esri, Maxar, Earthstar Geographics";
const OSM_URL = "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png";
const OSM_ATTR = "© OpenStreetMap contributors";

export default function MapTrack({ geojson }) {
  const mapEl = useRef(null);
  const mapRef = useRef(null);
  const baseRef = useRef(null);
  const [satellite, setSatellite] = useState(true);

  // init map once
  useEffect(() => {
    if (mapRef.current || !mapEl.current) return;
    const map = L.map(mapEl.current, { scrollWheelZoom: true });
    mapRef.current = map;
    baseRef.current = L.tileLayer(SAT_URL, { attribution: SAT_ATTR, maxZoom: 19 }).addTo(map);
    map.setView([20, 0], 2);
    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);

  // swap base layer
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    if (baseRef.current) map.removeLayer(baseRef.current);
    baseRef.current = satellite
      ? L.tileLayer(SAT_URL, { attribution: SAT_ATTR, maxZoom: 19 })
      : L.tileLayer(OSM_URL, { attribution: OSM_ATTR, maxZoom: 19 });
    baseRef.current.addTo(map);
  }, [satellite]);

  // draw track
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    if (map._trackLayer) {
      map.removeLayer(map._trackLayer);
      map._trackLayer = null;
    }
    if (!geojson || !geojson.coordinates || geojson.coordinates.length < 2) return;
    const latlngs = geojson.coordinates.map(([lon, lat]) => [lat, lon]);
    const group = L.layerGroup();
    L.polyline(latlngs, { color: "#38bdf8", weight: 3, opacity: 0.9 }).addTo(group);
    L.circleMarker(latlngs[0], {
      radius: 6,
      color: "#22c55e",
      fillColor: "#22c55e",
      fillOpacity: 1,
    })
      .bindTooltip("Start")
      .addTo(group);
    L.circleMarker(latlngs[latlngs.length - 1], {
      radius: 6,
      color: "#ef4444",
      fillColor: "#ef4444",
      fillOpacity: 1,
    })
      .bindTooltip("End")
      .addTo(group);
    group.addTo(map);
    map._trackLayer = group;
    // Cap zoom so very short tracks don't zoom past available satellite imagery.
    map.fitBounds(L.latLngBounds(latlngs).pad(0.15), { maxZoom: 18 });
  }, [geojson]);

  const hasTrack = geojson && geojson.coordinates && geojson.coordinates.length >= 2;

  return (
    <div className="map-wrap">
      <div ref={mapEl} className="map" />
      <button
        className="map-toggle"
        onClick={() => setSatellite((s) => !s)}
        type="button"
      >
        {satellite ? "Map view" : "Satellite"}
      </button>
      {!hasTrack && <div className="map-overlay">No position data</div>}
    </div>
  );
}
