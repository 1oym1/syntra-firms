// Live hotspots over Sudan for the story site: GET /api/live
//
// Reads NASA FIRMS public "active fire" files (last 24 h, no MAP_KEY needed) for MODIS, VIIRS NOAA-20 and
// VIIRS NOAA-21, and cleans them like the app (syntra.clean): inside Sudan's border, MODIS confidence >= 30 or
// VIIRS nominal/high, static heat sources (the app's 1 km static mask) removed. The FIRMS files have no CORS
// header, so the browser cannot read them directly; this function relays them. The CDN keeps the answer
// 30 min, so FIRMS sees at most a couple of requests an hour whatever the traffic.
import S from "./sudan_data.mjs";

const BASE = "https://firms.modaps.eosdis.nasa.gov/data/active_fire/";
const REGION = "_Northern_and_Central_Africa_24h.csv";
const FILES = {
  MODIS: "modis-c6.1/csv/MODIS_C6_1",
  VIIRS_NOAA20: "noaa-20-viirs-c2/csv/J1_VIIRS_C2",
  VIIRS_NOAA21: "noaa-21-viirs-c2/csv/J2_VIIRS_C2",
};
const MASK = new Set(S.mask);
const [X0, Y0, X1, Y1] = S.bbox;

function inside(x, y) {                       // even-odd rule over all rings (holes included)
  let c = false;
  for (const r of S.rings) {
    for (let i = 0, j = r.length - 1; i < r.length; j = i++) {
      const [xi, yi] = r[i], [xj, yj] = r[j];
      if ((yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) c = !c;
    }
  }
  return c;
}

function maskCell(lat, lon) {                 // same integer as syntra.clean.cell_id(lat, lon, 0.01)
  return Math.floor((lat + 90) / S.mask_deg) * 100000 + Math.floor((lon + 180) / S.mask_deg);
}

function clean(text, sensor) {
  const lines = text.split("\n");
  const h = lines[0].trim().split(",");
  const at = (n) => h.indexOf(n);
  const iLat = at("latitude"), iLon = at("longitude"), iConf = at("confidence");
  const iDate = at("acq_date"), iTime = at("acq_time"), iFrp = at("frp");
  const out = [];
  let newest = "";
  for (let k = 1; k < lines.length; k++) {
    const f = lines[k].split(",");
    if (f.length < h.length) continue;
    const lat = +f[iLat], lon = +f[iLon];
    if (!(lon >= X0 && lon <= X1 && lat >= Y0 && lat <= Y1)) continue;
    const conf = f[iConf].trim();
    const ok = sensor === "MODIS" ? +conf >= S.modis_conf : (conf === "nominal" || conf === "high" || conf === "n" || conf === "h");
    if (!ok || !inside(lon, lat) || MASK.has(maskCell(lat, lon))) continue;
    const when = f[iDate] + "T" + f[iTime].padStart(4, "0").replace(/(\d\d)(\d\d)/, "$1:$2") + "Z";
    if (when > newest) newest = when;
    // [lon, lat, sensor, pass time in minutes since 1970 UTC, fire radiative power in MW]
    out.push([Math.round(lon * 1e3) / 1e3, Math.round(lat * 1e3) / 1e3, sensor, Math.round(Date.parse(when) / 6e4),
      iFrp >= 0 ? Math.round(+f[iFrp] * 10) / 10 : null]);
  }
  return { points: out, newest };
}

export default async () => {
  const got = await Promise.allSettled(Object.entries(FILES).map(async ([sensor, path]) => {
    try {
      const r = await fetch(BASE + path + REGION, { signal: AbortSignal.timeout(9000) });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      return [sensor, clean(await r.text(), sensor)];
    } catch (e) { throw { sensor, message: `${sensor}: ${e && e.message || e}` }; }
  }));
  const all = [], by_sensor = {}, errors = [], missing = [];
  let newest = "";
  for (const g of got) {
    if (g.status === "rejected") { errors.push(String(g.reason && g.reason.message || g.reason)); missing.push(g.reason && g.reason.sensor); continue; }
    const [sensor, res] = g.value;
    by_sensor[sensor] = 0;
    all.push(...res.points);
    if (res.newest > newest) newest = res.newest;
  }
  // FIRMS "24h" files can still hold passes up to ~34 h old; keep the 24 h before the newest pass
  const cut = newest ? Math.round(Date.parse(newest) / 6e4) - 24 * 60 : -Infinity;
  const points = all.filter((p) => p[3] > cut);
  const dropped_older_than_24h = all.length - points.length;
  for (const p of points) by_sensor[p[2]] += 1;
  const body = {
    source: "NASA FIRMS active fire data, last 24 h (MODIS C6.1, VIIRS NOAA-20 and NOAA-21 C2, NRT)",
    window: "24h", fetched_utc: new Date().toISOString(), newest_pass_utc: newest || null,
    total: points.length, by_sensor, dropped_older_than_24h, missing, errors, points,
  };
  const ok = errors.length < Object.keys(FILES).length;
  return new Response(JSON.stringify(body), {
    status: ok ? 200 : 502,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "access-control-allow-origin": "*",
      "cache-control": "public, max-age=300",
      // cache at Netlify's edge: fresh for 30 min, then served stale while one request refreshes it
      // a partial answer (one satellite file timed out) is kept only 2 min so the next visitor retries
      "netlify-cdn-cache-control": !ok ? "no-store" : errors.length ? "public, s-maxage=120" : "public, s-maxage=1800, stale-while-revalidate=3600, durable",
    },
  });
};

export const config = { path: "/api/live" };
