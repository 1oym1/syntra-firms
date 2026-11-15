// Recent weather over Sudan's fire belt for the early-alert panel: GET /api/weather
//
// NASA POWER daily point data (no key): relative humidity, temperature, wind and rain at 2 m for the last
// 14 days at the same 4 fire-belt points the 25-year baseline in alerts.js uses (scripts/alert_baseline.py).
// POWER's daily values arrive with a lag of a few days; days not filled yet (-999) are dropped.
// The CDN keeps the answer 6 hours.
const PTS = [[24.5, 12.0], [29.5, 11.0], [32.5, 12.5], [34.5, 11.8]];
const PAR = ["RH2M", "T2M", "WS2M", "PRECTOTCORR"];

const ymd = (d) => d.toISOString().slice(0, 10).replace(/-/g, "");

export default async () => {
  const end = new Date(), start = new Date(Date.now() - 14 * 864e5);
  const got = await Promise.allSettled(PTS.map(async ([lon, lat]) => {
    const url = `https://power.larc.nasa.gov/api/temporal/daily/point?parameters=${PAR.join(",")}` +
      `&community=AG&longitude=${lon}&latitude=${lat}&start=${ymd(start)}&end=${ymd(end)}&format=JSON`;
    const r = await fetch(url, { signal: AbortSignal.timeout(12000) });
    if (!r.ok) throw new Error(`POWER ${r.status}`);
    return (await r.json()).properties.parameter;
  }));
  const ok = got.filter((g) => g.status === "fulfilled").map((g) => g.value);
  const days = {};
  for (const p of ok) {
    for (const date of Object.keys(p.RH2M)) {
      const v = PAR.map((k) => p[k][date]);
      if (v.some((x) => x === -999 || x == null)) continue;
      (days[date] ||= []).push(v);
    }
  }
  const out = Object.keys(days).sort()
    .filter((d) => days[d].length === ok.length)                       // only days every point has
    .map((d) => [`${d.slice(0, 4)}-${d.slice(4, 6)}-${d.slice(6)}`,
      ...PAR.map((_, i) => +(days[d].reduce((s, v) => s + v[i], 0) / days[d].length).toFixed(2))]);
  const body = {
    source: "NASA POWER daily (MERRA-2 / GEOS), mean of 4 fire-belt points", points: PTS,
    fields: ["date", ...PAR], fetched_utc: new Date().toISOString(), days: out,
    errors: got.filter((g) => g.status === "rejected").length,
  };
  const good = ok.length > 0 && out.length > 0;
  return new Response(JSON.stringify(body), {
    status: good ? 200 : 502,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "access-control-allow-origin": "*",
      "cache-control": "public, max-age=600",
      "netlify-cdn-cache-control": good ? "public, s-maxage=21600, stale-while-revalidate=43200, durable" : "no-store",
    },
  });
};

export const config = { path: "/api/weather" };
