from app.sources import _verified_record

def test_api_record_is_platform_verified_with_permalink():
    row = _verified_record("hackernews", "123", "headphones", "Nice", "https://news.ycombinator.com/item?id=123", "2026-11-04T10:00:00Z", 2, "user1")
    assert row["verification_status"] == "verified_api"
    assert row["trust_score"] == 100
    assert row["verification_details"]["retrieval"] == "official_platform_api"

def test_missing_permalink_is_only_partially_verified():
    row = _verified_record("stackoverflow", "abc", "laptop", "Nice", None, None)
    assert row["verification_status"] == "partially_verified"
    assert row["trust_score"] < 100
