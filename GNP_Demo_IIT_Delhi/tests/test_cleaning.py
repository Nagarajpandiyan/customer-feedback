from app.common import clean_text

def test_html():
    assert clean_text("<b>Hello&nbsp; world</b>") == "Hello world"

def test_url_and_email():
    result=clean_text("Mail a@b.com https://example.com")
    assert "[EMAIL]" in result and "[URL]" in result
