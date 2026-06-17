import pytest
from fastapi.testclient import TestClient
from app.main import create_app


@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(db_path=str(tmp_path / "t.db")))


def test_shorten_validates_url(client):
    assert client.post("/api/shorten", json={"url": "not-a-url"}).status_code == 422


def test_shorten_and_redirect_and_count(client):
    r = client.post("/api/shorten", json={"url": "https://example.com/page"})
    assert r.status_code == 200
    code = r.json()["code"]
    assert r.json()["short_url"].endswith(code)

    # follow it (no auto-redirect so we can inspect)
    follow = client.get(f"/{code}", follow_redirects=False)
    assert follow.status_code == 302
    assert follow.headers["location"] == "https://example.com/page"

    # click is recorded
    stats = client.get(f"/api/stats/{code}").json()
    assert stats["clicks"] == 1
    assert stats["target"] == "https://example.com/page"
    assert len(stats["by_day"]) == 1


def test_unknown_code_404(client):
    assert client.get("/api/stats/zzz").status_code == 404
    assert client.get("/nope", follow_redirects=False).status_code == 404


def test_links_listing(client):
    client.post("/api/shorten", json={"url": "https://a.com"})
    client.post("/api/shorten", json={"url": "https://b.com"})
    links = client.get("/api/links").json()
    assert len(links) == 2
    assert {l["target"] for l in links} == {"https://a.com", "https://b.com"}


def test_custom_alias(client):
    r = client.post("/api/shorten", json={"url": "https://example.com", "alias": "promo"})
    assert r.status_code == 200 and r.json()["code"] == "promo"
    assert client.get("/promo", follow_redirects=False).headers["location"] == "https://example.com"
    # taken alias -> 409
    dup = client.post("/api/shorten", json={"url": "https://other.com", "alias": "promo"})
    assert dup.status_code == 409


def test_invalid_and_reserved_alias_rejected(client):
    assert client.post("/api/shorten", json={"url": "https://e.com", "alias": "has space"}).status_code == 400
    assert client.post("/api/shorten", json={"url": "https://e.com", "alias": "api"}).status_code == 400


def test_shorten_is_idempotent_for_same_url(client):
    a = client.post("/api/shorten", json={"url": "https://same.com/x"}).json()["code"]
    b = client.post("/api/shorten", json={"url": "https://same.com/x"}).json()["code"]
    assert a == b
    assert len(client.get("/api/links").json()) == 1   # not duplicated


def test_auto_code_avoids_alias_collision(client):
    # claim the alias that the first auto-link would otherwise receive
    from app.shortcode import encode
    client.post("/api/shorten", json={"url": "https://taken.com", "alias": encode(1001)})
    r = client.post("/api/shorten", json={"url": "https://fresh.com"})
    assert r.status_code == 200
    assert r.json()["code"] != encode(1001)
    assert client.get(f"/{r.json()['code']}", follow_redirects=False).headers["location"] == "https://fresh.com"


def test_stats_top_referrers(client):
    code = client.post("/api/shorten", json={"url": "https://ref.com"}).json()["code"]
    client.get(f"/{code}", headers={"referer": "https://news.example"}, follow_redirects=False)
    client.get(f"/{code}", headers={"referer": "https://news.example"}, follow_redirects=False)
    client.get(f"/{code}", follow_redirects=False)   # direct
    stats = client.get(f"/api/stats/{code}").json()
    top = {r["referrer"]: r["clicks"] for r in stats["top_referrers"]}
    assert top["https://news.example"] == 2 and top["(direct)"] == 1
