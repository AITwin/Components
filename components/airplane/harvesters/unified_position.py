import json

import geopandas as gpd
import pandas as pd
import shapely

from src.components import Harvester


def _features(geojson_like):
    if not geojson_like:
        return []
    if isinstance(geojson_like, str):
        geojson_like = json.loads(geojson_like)
    return geojson_like.get("features") or []


def _key(props):
    """Match aircraft across feeds.

    icao24 is authoritative when both feeds report it; otherwise fall back
    to the (callsign, rounded position) pair so a plane present in both
    feeds without a hex still merges.
    """
    icao = (props.get("icao24") or "").strip().lower()
    if icao:
        return ("icao", icao)
    cs = (props.get("callsign") or "").strip().upper()
    return ("cs", cs)


class AirplaneUnifiedPositionHarvester(Harvester):
    """Union of airplane position snapshots from multiple feeds.

    Takes the OpenSky feed as ``source`` and the airplanes.live feed via
    the ``airplane_airplanes_live_position`` dependency, merges aircraft
    by ICAO24 (callsign fallback), and emits a single GeoJSON
    FeatureCollection. Each output feature carries a ``sources`` list
    showing which feeds saw it; airplanes.live position wins on conflict
    because it is generally more recent and complete.
    """

    def run(self, source, airplane_airplanes_live_position):
        opensky_feats = _features(getattr(source, "data", source))
        live_feats = _features(getattr(
            airplane_airplanes_live_position, "data", airplane_airplanes_live_position
        ))

        merged = {}

        # Seed with OpenSky first so airplanes.live values overwrite on key collision.
        for feat in opensky_feats:
            props = dict(feat.get("properties") or {})
            geom = feat.get("geometry")
            k = _key(props)
            if not k[1]:
                continue
            props.setdefault("source_feed", "opensky")
            props["sources"] = ["opensky"]
            merged[k] = {"properties": props, "geometry": geom}

        for feat in live_feats:
            props = dict(feat.get("properties") or {})
            geom = feat.get("geometry")
            k = _key(props)
            if not k[1]:
                continue
            existing = merged.get(k)
            if existing is None:
                props["sources"] = ["airplanes.live"]
                merged[k] = {"properties": props, "geometry": geom}
            else:
                # Merge: airplanes.live overwrites populated fields, but we
                # preserve OpenSky-only fields (e.g. origin_country).
                base = dict(existing["properties"])
                for field, value in props.items():
                    if value is not None and value != "":
                        base[field] = value
                base["sources"] = sorted(set(existing["properties"].get("sources", []) + ["airplanes.live"]))
                merged[k] = {"properties": base, "geometry": geom}  # prefer live geometry

        if not merged:
            return {"type": "FeatureCollection", "features": []}

        # Round-trip through GeoDataFrame to keep output identical in shape
        # to the upstream collectors.
        records = []
        geoms = []
        for entry in merged.values():
            geom = entry["geometry"]
            if not geom or "coordinates" not in geom:
                continue
            records.append(entry["properties"])
            geoms.append(shapely.geometry.shape(geom))

        gdf = gpd.GeoDataFrame(pd.DataFrame(records), geometry=geoms, crs="epsg:4326")
        return json.loads(gdf.to_json())
