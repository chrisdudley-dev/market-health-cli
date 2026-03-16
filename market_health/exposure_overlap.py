from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping

from market_health.market_catalog import get_symbol_meta


@dataclass(frozen=True)
class OverlapAssessment:
    from_symbol: str
    to_symbol: str
    overlap_class: str
    overlap_score: float
    same_market: bool
    same_region: bool
    same_family: bool
    same_bucket: bool
    reason: str


def _normalize_ctx(symbol: str, ctx: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "symbol": str(ctx.get("symbol") or symbol).strip().upper(),
        "market": str(ctx.get("market") or "").strip().upper(),
        "region": str(ctx.get("region") or "").strip().upper(),
        "family_id": str(ctx.get("family_id") or "").strip(),
        "bucket_id": str(ctx.get("bucket_id") or "").strip(),
        "kind": str(ctx.get("kind") or "").strip(),
        "taxonomy": str(ctx.get("taxonomy") or "").strip(),
    }


def _symbol_meta_dict(
    symbol: str,
    context_by_symbol: Mapping[str, Mapping[str, Any]] | None = None,
) -> Dict[str, Any] | None:
    sym_u = symbol.strip().upper()

    if context_by_symbol:
        row = context_by_symbol.get(sym_u) or context_by_symbol.get(symbol)
        if isinstance(row, Mapping):
            return _normalize_ctx(sym_u, row)

    meta = get_symbol_meta(sym_u)
    if meta is None:
        return None

    return {
        "symbol": meta.symbol,
        "market": meta.market,
        "region": meta.region,
        "family_id": meta.family_id,
        "bucket_id": meta.bucket_id,
        "kind": meta.kind,
        "taxonomy": meta.taxonomy,
    }


def assess_symbol_overlap(
    from_symbol: str,
    to_symbol: str,
    *,
    context_by_symbol: Mapping[str, Mapping[str, Any]] | None = None,
) -> OverlapAssessment:
    fs = from_symbol.strip().upper()
    ts = to_symbol.strip().upper()

    from_meta = _symbol_meta_dict(fs, context_by_symbol=context_by_symbol)
    to_meta = _symbol_meta_dict(ts, context_by_symbol=context_by_symbol)

    if from_meta is None or to_meta is None:
        return OverlapAssessment(
            from_symbol=fs,
            to_symbol=ts,
            overlap_class="unknown",
            overlap_score=0.50,
            same_market=False,
            same_region=False,
            same_family=False,
            same_bucket=False,
            reason="symbol_metadata_missing",
        )

    same_market = from_meta["market"] == to_meta["market"]
    same_region = from_meta["region"] == to_meta["region"]
    same_family = from_meta["family_id"] == to_meta["family_id"]
    same_bucket = from_meta["bucket_id"] == to_meta["bucket_id"]

    if same_bucket and same_market:
        overlap_class = "same_bucket_same_market"
        overlap_score = 1.00
        reason = "same bucket and same market"
    elif same_family and same_region:
        overlap_class = "same_family_same_region"
        overlap_score = 0.75
        reason = "same family and same region"
    elif same_family and not same_region:
        overlap_class = "same_family_different_region"
        overlap_score = 0.40
        reason = "same family but different region"
    elif not same_family and not same_region:
        overlap_class = "different_family_different_region"
        overlap_score = 0.00
        reason = "different family and different region"
    else:
        overlap_class = "mixed_overlap"
        overlap_score = 0.25
        reason = "mixed market/family/region overlap"

    return OverlapAssessment(
        from_symbol=fs,
        to_symbol=ts,
        overlap_class=overlap_class,
        overlap_score=overlap_score,
        same_market=same_market,
        same_region=same_region,
        same_family=same_family,
        same_bucket=same_bucket,
        reason=reason,
    )


def overlap_allowed(
    from_symbol: str,
    to_symbol: str,
    *,
    max_overlap_score: float = 0.75,
    context_by_symbol: Mapping[str, Mapping[str, Any]] | None = None,
) -> tuple[bool, OverlapAssessment]:
    assessment = assess_symbol_overlap(
        from_symbol,
        to_symbol,
        context_by_symbol=context_by_symbol,
    )
    allowed = assessment.overlap_score <= float(max_overlap_score)
    return allowed, assessment
