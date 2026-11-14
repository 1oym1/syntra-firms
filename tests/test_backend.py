"""Backend checks (NFR2, NFR10, NFR11, NFR13). Run from the repo root:  python -m pytest tests -q

Tests that need Sudan's data pack are skipped when it has not been built (python -m syntra.datapack).
"""
import numpy as np
import pandas as pd
import pytest
import requests

from syntra import analysis as a
from syntra import datapack, live, nrt

HAVE_PACK = (datapack.APP_DIR / "Sudan" / "manifest.json").exists()
needs_pack = pytest.mark.skipif(not HAVE_PACK, reason="no data pack: python -m syntra.datapack")


@pytest.fixture(scope="module")
def pack():
    return datapack.load("Sudan")


# ---------------------------------------------------------------- status rules (no data needed)
@pytest.mark.parametrize("value,history,expected", [
    (200, list(range(90, 111)), "Very high"),       # median 100, 90th percentile 108
    (160, list(range(50, 201)), "Above normal"),    # median 125 (+28 %), under the 90th percentile 185
    (115, list(range(90, 111)) + [150] * 3, "Normal"),   # +13 %, under the 90th percentile
    (85, [90, 100, 110] * 4, "Normal"),             # -15 %
    (70, [100] * 10, "Below normal"),               # -30 %
    (102, [100] * 10, "Very high"),                 # every earlier year was 100: anything above is a record
    (5, [], "No baseline yet"),
])
def test_status_rules(value, history, expected):
    assert a.status(a.compare(value, history)) == expected


def test_rank_one_is_highest():
    assert a.compare(10, [1, 2, 3])["rank"] == 1
    assert a.compare(0, [1, 2, 3])["rank"] == 4


# ---------------------------------------------------------------- one unit, same numbers everywhere (NFR13)
@needs_pack
def test_daily_adds_up_to_monthly(pack):
    d = a.daily_series(pack["celldays"], pack["factors"])
    mon = d.groupby(d.index.to_period("M")).sum()
    s = a.monthly(pack["series"])
    assert np.allclose(mon.reindex(s.index).to_numpy(), s.to_numpy(), atol=1e-6)


@needs_pack
def test_month_so_far_matches_series_for_the_part_month(pack):
    m = a.month_to_date(pack["celldays"], pack["factors"])
    s = a.monthly(pack["series"])
    assert m["value"] == pytest.approx(s[pd.Period(m["last_day"], freq="M")])


@needs_pack
def test_celldays_hold_the_rows_harmonize_counts(pack):
    s = pack["series"]
    cd = pack["celldays"]
    v = cd[cd.family == "VIIRS"].drop_duplicates(["acq_date", "cell_id"]).groupby(["year", "month"]).size()
    got = v.reindex(pd.MultiIndex.from_frame(s[["year", "month"]]), fill_value=0).to_numpy()
    assert np.array_equal(got, s.viirs_cells.to_numpy().astype(int))


# ---------------------------------------------------------------- honest accuracy (NFR2, NFR11)
@needs_pack
def test_heldout_accuracy(pack):
    sc = a.hz.scores(pack["series"])
    assert sc["r2"] >= 0.8 and sc["r2_anom"] > 0.5
    assert pack["validation"]["annual_error_%"].abs().median() < 10


@needs_pack
def test_no_2012_jump(pack):
    y = a.annual_totals(a.monthly(pack["series"]))
    assert 0.8 < y.loc[2012:2014].mean() / y.loc[2009:2011].mean() < 1.25


# ---------------------------------------------------------------- map toggles
@needs_pack
def test_static_toggle_splits_cleanly(pack):
    p = live.historical_points(pack, "2025-01-01", "2025-12-31", sensors=list(live.LIVE_SOURCES), include_static=True)
    veg = live.filter_points(p, list(live.LIVE_SOURCES), include_static=False)
    assert len(veg) + int(p.is_static.sum()) == len(p)
    assert not veg.is_static.any()


@needs_pack
def test_sensor_toggle(pack):
    p = live.historical_points(pack, "2025-11-01", "2025-11-30", sensors=["MODIS", "VIIRS_SNPP"], include_static=True)
    m = live.filter_points(p, ["MODIS"], True)
    v = live.filter_points(p, ["VIIRS_SNPP"], True)
    assert set(m.sensor) == {"MODIS"} and set(v.sensor) == {"VIIRS_SNPP"}
    assert len(m) + len(v) == len(p)


# ---------------------------------------------------------------- risk periods
@needs_pack
def test_risk_periods_shape(pack):
    r = a.risk_periods(a.daily_series(pack["celldays"], pack["factors"]))
    w = r["weeks"]
    assert len(w) == 52 and w.share_of_years_pct.between(0, 100).all()
    assert r["periods"] and r["periods"][0]["class"] in ("Extreme", "High", "Moderate")


# ---------------------------------------------------------------- the key never leaks (NFR10)
def test_live_error_hides_key(monkeypatch):
    secret = "SECRETKEY1234567890"
    monkeypatch.setattr(nrt, "map_key", lambda: secret)
    monkeypatch.setattr(live, "_country", lambda c: (type("S", (), {"bounds": (21.8, 8.7, 38.6, 22.2)})(), None))

    def boom(url, timeout):
        raise requests.ConnectionError(f"failed: {url}")
    monkeypatch.setattr(live.requests, "get", boom)
    monkeypatch.setattr(live, "LIVE_DIR", datapack.REPO_ROOT / "data" / "raw" / "live_test_never_written")
    with pytest.raises(RuntimeError) as e:
        live.live_points(days=1, sensors=["MODIS"], today=pd.Timestamp("2026-11-14").date())
    assert secret not in str(e.value)
