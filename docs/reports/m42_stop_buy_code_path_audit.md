# M42 Stop/Buy Code Path Audit

## Operator contract

- `Stop` is the actionable broker stop-loss trigger.
- `Buy` is the actionable broker stop-buy trigger.
- Dashboard output must remain simple: no additional user-facing columns are required for M42.
- Hidden math may become more complex, but the table remains `Stop` and `Buy`.

## Current finding

The current terminal `Stop` and `Buy` values are not yet based on clustered support/resistance confluence.

The current legacy dashboard path uses a simple recent range plus ATR buffer fallback:

```text
ATR = 14-period rolling average true range
support_cushion_atr = (last_close - recent_low) / ATR
overhead_resistance_atr = (recent_high - last_close) / ATR
stop = recent_low - 0.25 * ATR
buy = recent_high + 0.25 * ATR
```

This proves the current primary dashboard behavior is closer to recent-low/recent-high fallback logic than the intended multi-candidate clustered floor/ceiling model.

## Required future behavior

The intended M42 behavior is:

```text
Stop = selected_support_cluster_floor - ATR_buffer
Buy = selected_resistance_cluster_ceiling + ATR_buffer
```

Where ATR is only the buffer/normalizer, not the source of the floor or ceiling.

## Scope guard

M42 must not:
- add more terminal columns
- redesign ranking
- change C/H1/H5 scoring
- introduce swap-candidate logic

## Source grep evidence

```text
market_health/__init__.py:54:    Supports offline test injection:
market_health/dashboard_legacy.py:224:            # stop skipping when we hit the Pi Grid header
market_health/dashboard_legacy.py:840:    atr = tr.rolling(14, min_periods=5).mean()
market_health/dashboard_legacy.py:841:    if atr.empty:
market_health/dashboard_legacy.py:844:    atr_last = float(atr.iloc[-1])
market_health/dashboard_legacy.py:852:    support_cushion_atr = max(0.0, (last_close - recent_low) / atr_last)
market_health/dashboard_legacy.py:853:    overhead_resistance_atr = max(0.0, (recent_high - last_close) / atr_last)
market_health/dashboard_legacy.py:855:    stop = recent_low - (0.25 * atr_last)
market_health/dashboard_legacy.py:856:    buy = recent_high + (0.25 * atr_last)
market_health/dashboard_legacy.py:859:    if support_cushion_atr <= 0.25:
market_health/dashboard_legacy.py:861:    elif support_cushion_atr <= 0.75:
market_health/dashboard_legacy.py:864:    if overhead_resistance_atr <= 0.25:
market_health/dashboard_legacy.py:866:    elif overhead_resistance_atr <= 1.00:
market_health/dashboard_legacy.py:870:        "support_cushion_atr": round(support_cushion_atr, 6),
market_health/dashboard_legacy.py:871:        "support_atr": round(support_cushion_atr, 6),
market_health/dashboard_legacy.py:872:        "sup_atr": round(support_cushion_atr, 6),
market_health/dashboard_legacy.py:873:        "overhead_resistance_atr": round(overhead_resistance_atr, 6),
market_health/dashboard_legacy.py:874:        "resistance_atr": round(overhead_resistance_atr, 6),
market_health/dashboard_legacy.py:875:        "res_atr": round(overhead_resistance_atr, 6),
market_health/dashboard_legacy.py:878:        "stop": round(stop, 6),
market_health/dashboard_legacy.py:879:        "stop_candidate": round(stop, 6),
market_health/dashboard_legacy.py:880:        "catastrophic_stop_candidate": round(stop, 6),
market_health/dashboard_legacy.py:881:        "buy": round(buy, 6),
market_health/dashboard_legacy.py:882:        "buy_candidate": round(buy, 6),
market_health/dashboard_legacy.py:883:        "stop_buy_candidate": round(buy, 6),
market_health/dashboard_legacy.py:884:        "breakout_trigger": round(buy, 6),
market_health/dashboard_legacy.py:946:            ss.get("support_cushion_atr")
market_health/dashboard_legacy.py:948:                ss, ["support_cushion_atr", "support_atr", "sup_atr", "supatr"]
market_health/dashboard_legacy.py:951:                payload, ["support_cushion_atr", "support_atr", "sup_atr", "supatr"]
market_health/dashboard_legacy.py:955:            ss.get("overhead_resistance_atr")
market_health/dashboard_legacy.py:957:                ss, ["overhead_resistance_atr", "resistance_atr", "res_atr", "resatr"]
market_health/dashboard_legacy.py:961:                ["overhead_resistance_atr", "resistance_atr", "res_atr", "resatr"],
market_health/dashboard_legacy.py:980:        stop = (
market_health/dashboard_legacy.py:982:            or ss.get("catastrophic_stop_candidate")
market_health/dashboard_legacy.py:986:                    "stop",
market_health/dashboard_legacy.py:988:                    "catastrophic_stop_candidate",
market_health/dashboard_legacy.py:995:                    "stop",
market_health/dashboard_legacy.py:997:                    "catastrophic_stop_candidate",
market_health/dashboard_legacy.py:1002:        buy = (
market_health/dashboard_legacy.py:1004:            or ss.get("breakout_trigger")
market_health/dashboard_legacy.py:1006:                ss, ["buy", "buy_candidate", "stop_buy_candidate", "breakout_trigger"]
market_health/dashboard_legacy.py:1010:                ["buy", "buy_candidate", "stop_buy_candidate", "breakout_trigger"],
market_health/dashboard_legacy.py:1016:            for v in (sup, res, state_tags, state_text, stop, buy)
market_health/dashboard_legacy.py:1019:            out.setdefault("support_cushion_atr", sup)
market_health/dashboard_legacy.py:1020:            out.setdefault("support_atr", sup)
market_health/dashboard_legacy.py:1022:            out.setdefault("overhead_resistance_atr", res)
market_health/dashboard_legacy.py:1023:            out.setdefault("resistance_atr", res)
market_health/dashboard_legacy.py:1032:            out.setdefault("stop", stop)
market_health/dashboard_legacy.py:1033:            out.setdefault("stop_candidate", stop)
market_health/dashboard_legacy.py:1034:            out.setdefault("catastrophic_stop_candidate", stop)
market_health/dashboard_legacy.py:1035:            out.setdefault("buy", buy)
market_health/dashboard_legacy.py:1036:            out.setdefault("buy_candidate", buy)
market_health/dashboard_legacy.py:1037:            out.setdefault("stop_buy_candidate", buy)
market_health/dashboard_legacy.py:1038:            out.setdefault("breakout_trigger", buy)
market_health/dashboard_legacy.py:1473:            ss.get("support_cushion_atr") if isinstance(ss, dict) else None,
market_health/dashboard_legacy.py:1474:            ss.get("support_atr") if isinstance(ss, dict) else None,
market_health/dashboard_legacy.py:1478:            row.get("support_atr"),
market_health/dashboard_legacy.py:1479:            proxy_row.get("support_atr"),
market_health/dashboard_legacy.py:1482:            ss.get("overhead_resistance_atr") if isinstance(ss, dict) else None,
market_health/dashboard_legacy.py:1483:            ss.get("resistance_atr") if isinstance(ss, dict) else None,
market_health/dashboard_legacy.py:1487:            row.get("resistance_atr"),
market_health/dashboard_legacy.py:1488:            proxy_row.get("resistance_atr"),
market_health/dashboard_legacy.py:1501:        stop = _first_num(
market_health/dashboard_legacy.py:1503:            ss.get("catastrophic_stop_candidate") if isinstance(ss, dict) else None,
market_health/dashboard_legacy.py:1504:            ss.get("stop") if isinstance(ss, dict) else None,
market_health/dashboard_legacy.py:1506:        buy = _first_num(
market_health/dashboard_legacy.py:1508:            ss.get("breakout_trigger") if isinstance(ss, dict) else None,
market_health/dashboard_legacy.py:1509:            ss.get("buy") if isinstance(ss, dict) else None,
market_health/dashboard_legacy.py:1526:                "stop": stop,
market_health/dashboard_legacy.py:1527:                "buy": buy,
market_health/dashboard_legacy.py:1550:    tbl.add_column("SupATR", justify="right", no_wrap=True)
market_health/dashboard_legacy.py:1551:    tbl.add_column("ResATR", justify="right", no_wrap=True)
market_health/dashboard_legacy.py:1553:    tbl.add_column("Stop", justify="right", no_wrap=True)
market_health/dashboard_legacy.py:1554:    tbl.add_column("Buy", justify="right", no_wrap=True)
market_health/dashboard_legacy.py:1566:            Text(_fmt_num(r["stop"]), style=_num_style(r["stop"])),
market_health/dashboard_legacy.py:1567:            Text(_fmt_num(r["buy"]), style=_num_style(r["buy"])),
market_health/dashboard_legacy.py:1594:        "support_cushion_atr",
market_health/dashboard_legacy.py:1595:        "overhead_resistance_atr",
market_health/dashboard_legacy.py:1599:        "catastrophic_stop_candidate",
market_health/dashboard_legacy.py:1601:        "breakout_trigger",
market_health/engine.py:130:    "ATR%": ["d_atr_pct", "atr_pct_score", "atr_pct"],
market_health/engine.py:176:    "D": ["ATR%", "IV%", "Correlation", "Event Risk", "Gap Plan", "Sizing/RR"],
market_health/engine.py:206:    labels = ["ATR%", "IV%", "Correlation", "Event Risk", "Gap Plan", "Sizing/RR"]
market_health/engine.py:240:    # (1) ATR% (14)
market_health/engine.py:249:    atr = tr.ewm(span=14, adjust=False).mean()
market_health/engine.py:250:    atr_pct = (atr / close_ser) * 100
market_health/engine.py:259:    checks.append({"label": "ATR%", "score": score_atr})
market_health/engine.py:303:    # (6) Sizing/RR: |Close-EMA20| / ATR
market_health/engine.py:305:    if len(ema20.dropna()) and len(atr.dropna()) and float(atr.dropna().iloc[-1]) > 0:
market_health/engine.py:307:            atr.dropna().iloc[-1]
market_health/engine.py:640:    # ATR for normalization (14)
market_health/engine.py:645:    atr = tr.ewm(span=14, adjust=False).mean()
market_health/engine.py:673:    # 1) EM Fit: |Close-EMA20| / ATR (smaller is better)
market_health/engine.py:675:        float(abs(close.iloc[-1] - e20.iloc[-1])) / float(atr.iloc[-1])
market_health/engine.py:676:        if atr.iloc[-1] > 0
market_health/engine.py:679:    # ≤1.0 ATR = good, ≤2.0 ATR = neutral
market_health/forecast_checks_a_announcements.py:297:    atr = float(atrp14) if atrp14 is not None else 0.0
market_health/forecast_checks_a_announcements.py:306:    if z >= danger_z or width >= danger_width or atr >= danger_atr:
market_health/forecast_checks_a_announcements.py:308:    elif z >= warn_z or width >= warn_width or atr >= warn_atr:
market_health/forecast_checks_b_backdrop.py:50:        b4_support_cushion(
market_health/forecast_checks_b_backdrop.py:210:def b4_support_cushion(
market_health/forecast_checks_b_backdrop.py:219:    meaning = "How much room exists before key support breaks (buffer against normal pullbacks)?"
market_health/forecast_checks_b_backdrop.py:222:            "Support Cushion", meaning, "Insufficient history; neutral."
market_health/forecast_checks_b_backdrop.py:240:        "Support Cushion",
market_health/forecast_checks_b_backdrop.py:264:        "Is participation improving (more supportive flow/volume behavior), not fading?"
market_health/forecast_checks_d_danger.py:30:    support_cushion_proxy: Optional[float] = None,
market_health/forecast_checks_d_danger.py:72:            support_cushion_proxy=support_cushion_proxy,
market_health/forecast_checks_d_danger.py:100:            "Volatility Trend", meaning, "Missing ATR/IV/BB inputs; neutral."
market_health/forecast_checks_d_danger.py:157:        note = "used IV + ATR/BB"
market_health/forecast_checks_d_danger.py:173:            note = "iv.v1 status=ok but no symbol metrics; used ATR/BB proxies"
market_health/forecast_checks_d_danger.py:175:            note = f"iv.v1 missing (status={iv_status}); used ATR/BB proxies"
market_health/forecast_checks_d_danger.py:245:    atr = float(atrp14) if isinstance(atrp14, (int, float)) else 0.0
market_health/forecast_checks_d_danger.py:246:    atr_h = atr * h_scale
market_health/forecast_checks_d_danger.py:426:    atr = float(atrp14) if isinstance(atrp14, (int, float)) and atrp14 > 0 else 1.0
market_health/forecast_checks_d_danger.py:427:    room_atr = room_pct / atr
market_health/forecast_checks_d_danger.py:461:    support_cushion_proxy: Optional[float],
market_health/forecast_checks_d_danger.py:468:    if support_cushion_proxy is None:
market_health/forecast_checks_d_danger.py:472:            "Missing support cushion proxy; neutral.",
market_health/forecast_checks_d_danger.py:476:    atr = float(atrp14) if isinstance(atrp14, (int, float)) else 0.0
market_health/forecast_checks_d_danger.py:485:        support_cushion_proxy >= strong_cushion
market_health/forecast_checks_d_danger.py:487:        and atr <= high_atr
market_health/forecast_checks_d_danger.py:490:    elif support_cushion_proxy >= ok_cushion and corr <= warn_corr:
market_health/forecast_checks_d_danger.py:502:            "support_cushion_proxy": support_cushion_proxy,
market_health/forecast_features.py:262:def atr(
market_health/forecast_features.py:283:    a = atr(high, low, close, window)
market_health/forecast_score_provider.py:150:            context["atr"] = atr_now
market_health/forecast_score_provider.py:191:        structure_summary.get("nearest_support_zone")
market_health/forecast_score_provider.py:192:    ) or _has_zone_levels(structure_summary.get("nearest_resistance_zone"))
market_health/forecast_score_provider.py:300:        # ATR% and CLV
market_health/forecast_score_provider.py:369:            support_cushion_proxy = (
market_health/forecast_score_provider.py:399:                support_cushion_proxy=support_cushion_proxy,
market_health/market_catalog.py:20:    supports_sector_taxonomy: bool
market_health/market_catalog.py:21:    supports_inverse_etfs: bool
market_health/market_catalog.py:22:    supports_crowding_direct: str
market_health/market_catalog.py:41:    broker_profile: str = "us_retail_supported"
market_health/market_ui.py:53:    "D": ["ATR%", "IV%", "Correlation", "Event Risk", "Gap Plan", "Sizing/RR"],
market_health/market_ui.py:55:    "F": ["Trigger", "Invalidation", "Targets", "Time Stop", "Slippage", "Alerts"],
market_health/market_ui.py:168:    # ENV_V1_JSON_SUPPORT_V1: allow environment.v1.json (object) as input; use its sector list
market_health/market_ui.py:490:    Supports:
market_health/market_ui.py:738:            or rec.get("buy")
market_health/positions_sectorize.py:4:asset-family classification metadata for supported non-sector holdings.
market_health/positions_sectorize.py:75:      - supported_outside_universe: known supported holdings not currently scoreable
market_health/positions_sectorize.py:76:      - unmapped: unsupported originals ignored
market_health/positions_sectorize.py:84:    supported_outside_universe: List[str] = []
market_health/positions_sectorize.py:92:        "UNSUPPORTED": [],
market_health/positions_sectorize.py:129:        if asset_meta.group == "UNSUPPORTED":
market_health/positions_sectorize.py:132:            supported_outside_universe.append(sym)
market_health/positions_sectorize.py:141:        "supported_outside_universe": sorted(set(supported_outside_universe)),
market_health/rating.py:8:    label: str  # "Strong Buy"
market_health/rating.py:17:    ("Buy", "B"),
market_health/rating.py:18:    ("Strong Buy", "SB"),
market_health/refresh_snapshot.py:270:    # --- load cached supporting docs (positions, reco, forecast) ---
market_health/risk_overlay.py:31:    catastrophic_stop = _f(ss.get("catastrophic_stop_candidate"))
market_health/risk_overlay.py:33:    support_cushion_atr = _f(ss.get("support_cushion_atr"))
market_health/risk_overlay.py:42:            reason="No catastrophic stop candidate available from structure summary.",
market_health/risk_overlay.py:45:    if support_cushion_atr is not None and support_cushion_atr <= 0.5:
market_health/risk_overlay.py:54:            reason="Support cushion is tight; catastrophic overlay armed.",
market_health/risk_overlay.py:65:        reason="Catastrophic stop candidate exists, but overlay is not armed.",
market_health/structure_engine.py:70:    nearest_support_zone: StructureZone = field(default_factory=StructureZone)
market_health/structure_engine.py:71:    nearest_resistance_zone: StructureZone = field(default_factory=StructureZone)
market_health/structure_engine.py:73:    support_cushion_atr: float | None = None
market_health/structure_engine.py:74:    overhead_resistance_atr: float | None = None
market_health/structure_engine.py:76:    breakout_trigger: float | None = None
market_health/structure_engine.py:83:    catastrophic_stop_candidate: float | None = None
market_health/structure_engine.py:89:    support_cushion_sigma: float | None = None
market_health/structure_engine.py:90:    overhead_resistance_sigma: float | None = None
market_health/structure_engine.py:92:    support_confluence_count: int | None = None
market_health/structure_engine.py:93:    resistance_confluence_count: int | None = None
market_health/structure_engine.py:103:            "nearest_support_zone": {
market_health/structure_engine.py:104:                "lower": self.nearest_support_zone.lower,
market_health/structure_engine.py:105:                "center": self.nearest_support_zone.center,
market_health/structure_engine.py:106:                "upper": self.nearest_support_zone.upper,
market_health/structure_engine.py:107:                "weight": self.nearest_support_zone.weight,
market_health/structure_engine.py:109:            "nearest_resistance_zone": {
market_health/structure_engine.py:110:                "lower": self.nearest_resistance_zone.lower,
market_health/structure_engine.py:111:                "center": self.nearest_resistance_zone.center,
market_health/structure_engine.py:112:                "upper": self.nearest_resistance_zone.upper,
market_health/structure_engine.py:113:                "weight": self.nearest_resistance_zone.weight,
market_health/structure_engine.py:115:            "support_cushion_atr": self.support_cushion_atr,
market_health/structure_engine.py:116:            "overhead_resistance_atr": self.overhead_resistance_atr,
market_health/structure_engine.py:117:            "breakout_trigger": self.breakout_trigger,
market_health/structure_engine.py:122:            "catastrophic_stop_candidate": self.catastrophic_stop_candidate,
market_health/structure_engine.py:126:            "support_cushion_sigma": self.support_cushion_sigma,
market_health/structure_engine.py:127:            "overhead_resistance_sigma": self.overhead_resistance_sigma,
market_health/structure_engine.py:128:            "support_confluence_count": self.support_confluence_count,
market_health/structure_engine.py:129:            "resistance_confluence_count": self.resistance_confluence_count,
market_health/structure_engine.py:145:def _select_nearest_support_zone(
market_health/structure_engine.py:148:    supports = [zone for zone in zones if zone.kind == "support"]
market_health/structure_engine.py:149:    if not supports:
market_health/structure_engine.py:152:        return max(supports, key=lambda zone: zone.center)
market_health/structure_engine.py:153:    eligible = [zone for zone in supports if zone.center <= price]
market_health/structure_engine.py:156:    return max(supports, key=lambda zone: zone.center)
market_health/structure_engine.py:159:def _select_nearest_resistance_zone(
market_health/structure_engine.py:162:    resistances = [zone for zone in zones if zone.kind == "resistance"]
market_health/structure_engine.py:163:    if not resistances:
market_health/structure_engine.py:166:        return min(resistances, key=lambda zone: zone.center)
market_health/structure_engine.py:167:    eligible = [zone for zone in resistances if zone.center >= price]
market_health/structure_engine.py:170:    return min(resistances, key=lambda zone: zone.center)
market_health/structure_engine.py:176:    atr: float | None,
market_health/structure_engine.py:183:    atr_component = 0.25 * float(atr) if atr is not None and atr > 0 else 0.0
market_health/structure_engine.py:197:    support_cushion_atr: float | None,
market_health/structure_engine.py:198:    overhead_resistance_atr: float | None,
market_health/structure_engine.py:200:    if overhead_resistance_atr is None:
market_health/structure_engine.py:202:    if overhead_resistance_atr <= 0.5 and (
market_health/structure_engine.py:203:        support_cushion_atr is None or support_cushion_atr >= 0.5
market_health/structure_engine.py:206:    if overhead_resistance_atr <= 1.5:
market_health/structure_engine.py:211:def _breakdown_risk_bucket(*, support_cushion_atr: float | None) -> int:
market_health/structure_engine.py:212:    if support_cushion_atr is None:
market_health/structure_engine.py:214:    if support_cushion_atr <= 0.5:
market_health/structure_engine.py:216:    if support_cushion_atr <= 1.5:
market_health/structure_engine.py:224:    support_zone: ClusteredZone | None,
market_health/structure_engine.py:225:    support_cushion_atr: float | None,
market_health/structure_engine.py:226:    overhead_resistance_atr: float | None,
market_health/structure_engine.py:231:    if support_cushion_atr is not None and support_cushion_atr <= 0.5:
market_health/structure_engine.py:233:    if overhead_resistance_atr is not None and overhead_resistance_atr <= 0.5:
market_health/structure_engine.py:237:    if price is not None and support_zone is not None and support_zone.upper >= price:
market_health/structure_engine.py:279:    atr = context.get("atr")
market_health/structure_engine.py:363:    if price is not None and atr is not None:
market_health/structure_engine.py:367:                atr=float(atr),
market_health/structure_engine.py:376:        atr=atr,
market_health/structure_engine.py:385:            atr=atr,
market_health/structure_engine.py:393:    support_zone = _select_nearest_support_zone(zones, price=price)
market_health/structure_engine.py:394:    resistance_zone = _select_nearest_resistance_zone(zones, price=price)
market_health/structure_engine.py:396:    support_edge = support_zone.upper if support_zone is not None else None
market_health/structure_engine.py:397:    resistance_edge = resistance_zone.upper if resistance_zone is not None else None
market_health/structure_engine.py:399:    support_cushion_atr_raw = normalize_distance_atr(
market_health/structure_engine.py:401:        level=support_edge,
market_health/structure_engine.py:402:        atr=atr,
market_health/structure_engine.py:404:    support_cushion_atr = (
market_health/structure_engine.py:406:        if support_cushion_atr_raw is None
market_health/structure_engine.py:407:        else max(float(support_cushion_atr_raw), 0.0)
market_health/structure_engine.py:410:    overhead_resistance_atr_raw = (
market_health/structure_engine.py:412:        if price is None or resistance_edge is None or atr is None or atr <= 0
market_health/structure_engine.py:413:        else (float(resistance_edge) - float(price)) / float(atr)
market_health/structure_engine.py:415:    overhead_resistance_atr = (
market_health/structure_engine.py:417:        if overhead_resistance_atr_raw is None
market_health/structure_engine.py:418:        else max(float(overhead_resistance_atr_raw), 0.0)
market_health/structure_engine.py:421:    support_cushion_sigma_raw = normalize_distance_sigma(
market_health/structure_engine.py:423:        level=support_edge,
market_health/structure_engine.py:427:    support_cushion_sigma = (
market_health/structure_engine.py:429:        if support_cushion_sigma_raw is None
market_health/structure_engine.py:430:        else max(float(support_cushion_sigma_raw), 0.0)
market_health/structure_engine.py:433:    overhead_resistance_sigma_raw = (
market_health/structure_engine.py:437:            or resistance_edge is None
market_health/structure_engine.py:443:        else (float(resistance_edge) - float(price))
market_health/structure_engine.py:446:    overhead_resistance_sigma = (
market_health/structure_engine.py:448:        if overhead_resistance_sigma_raw is None
market_health/structure_engine.py:449:        else max(float(overhead_resistance_sigma_raw), 0.0)
market_health/structure_engine.py:453:        support_cushion_atr=support_cushion_atr,
market_health/structure_engine.py:454:        overhead_resistance_atr=overhead_resistance_atr,
market_health/structure_engine.py:457:        support_cushion_atr=support_cushion_atr,
market_health/structure_engine.py:464:        nearest_support_zone=_structure_zone_from_cluster(support_zone),
market_health/structure_engine.py:465:        nearest_resistance_zone=_structure_zone_from_cluster(resistance_zone),
market_health/structure_engine.py:466:        support_cushion_atr=support_cushion_atr,
market_health/structure_engine.py:467:        overhead_resistance_atr=overhead_resistance_atr,
market_health/structure_engine.py:468:        breakout_trigger=None if resistance_zone is None else resistance_zone.upper,
market_health/structure_engine.py:469:        breakdown_trigger=None if support_zone is None else support_zone.lower,
market_health/structure_engine.py:470:        reclaim_trigger=None if support_zone is None else support_zone.upper,
market_health/structure_engine.py:473:        catastrophic_stop_candidate=None
market_health/structure_engine.py:474:        if support_zone is None
```
