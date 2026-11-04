from app.sources import _verified_record

def test_public_api_record_has_provenance_fields():
    r = _verified_record('hackernews', '12345', 'headphones', 'Battery life is good',
        'https://news.ycombinator.com/item?id=12345', '2026-11-04T10:00:00Z', 5, 'someauthor')
    assert r['verification_status'] == 'verified_api'
    assert r['trust_score'] == 100
    assert r['verification_details']['retrieval'] == 'public_platform_api'

