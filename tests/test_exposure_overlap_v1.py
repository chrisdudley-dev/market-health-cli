from market_health.exposure_overlap import assess_symbol_overlap, overlap_allowed


CTX = {
    "JPTECH_A": {
        "market": "JP",
        "region": "APAC",
        "family_id": "technology",
        "bucket_id": "jp_tech_a",
    },
    "JPTECH_B": {
        "market": "JP",
        "region": "APAC",
        "family_id": "technology",
        "bucket_id": "jp_tech_a",
    },
    "JPTECH_C": {
        "market": "JP",
        "region": "APAC",
        "family_id": "technology",
        "bucket_id": "jp_tech_c",
    },
    "USTECH_A": {
        "market": "US",
        "region": "NA",
        "family_id": "technology",
        "bucket_id": "us_tech_a",
    },
    "USUTIL_A": {
        "market": "US",
        "region": "NA",
        "family_id": "utilities",
        "bucket_id": "us_util_a",
    },
}


def test_same_bucket_same_market_scores_highest_overlap() -> None:
    res = assess_symbol_overlap("JPTECH_A", "JPTECH_B", context_by_symbol=CTX)
    assert res.overlap_class == "same_bucket_same_market"
    assert res.same_bucket is True
    assert res.same_market is True
    assert res.overlap_score == 1.00


def test_same_family_same_region_detected() -> None:
    res = assess_symbol_overlap("JPTECH_A", "JPTECH_C", context_by_symbol=CTX)
    assert res.overlap_class == "same_family_same_region"
    assert res.same_family is True
    assert res.same_region is True
    assert res.overlap_score == 0.75


def test_same_family_different_region_is_partial_overlap() -> None:
    res = assess_symbol_overlap("USTECH_A", "JPTECH_A", context_by_symbol=CTX)
    assert res.overlap_class == "same_family_different_region"
    assert res.same_family is True
    assert res.same_region is False
    assert res.overlap_score == 0.40


def test_different_family_different_region_is_lowest_overlap() -> None:
    res = assess_symbol_overlap("USUTIL_A", "JPTECH_A", context_by_symbol=CTX)
    assert res.overlap_class == "different_family_different_region"
    assert res.same_family is False
    assert res.same_region is False
    assert res.overlap_score == 0.00


def test_overlap_allowed_blocks_only_above_threshold() -> None:
    ok1, a1 = overlap_allowed(
        "JPTECH_A",
        "JPTECH_B",
        max_overlap_score=0.75,
        context_by_symbol=CTX,
    )
    ok2, a2 = overlap_allowed(
        "USTECH_A",
        "JPTECH_A",
        max_overlap_score=0.75,
        context_by_symbol=CTX,
    )

    assert ok1 is False
    assert a1.overlap_class == "same_bucket_same_market"

    assert ok2 is True
    assert a2.overlap_class == "same_family_different_region"
