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
