"""The web server only answers pages opened from this computer, and reports never run HTML from their text."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from interviewer import server


@pytest.fixture
def app(make_round, dirs, monkeypatch):
    make_round("acme", "hm")
    monkeypatch.setattr(server, "ROOT", dirs.root)
    monkeypatch.setattr(server, "selection", None)
    monkeypatch.setattr(server, "active", None)
    monkeypatch.delenv("PIPECAT_ALLOWED_ORIGINS", raising=False)
    app = FastAPI()
    server.register(app)
    return app


@pytest.mark.parametrize("base_url", ["http://localhost:7860", "http://127.0.0.1:7860", "http://[::1]:7860"])
def test_pages_opened_from_this_computer_work(app, base_url):
    client = TestClient(app, base_url=base_url)
    assert client.get("/api/status").status_code == 200
    assert client.get("/api/status", headers={"Origin": base_url}).status_code == 200


def test_other_websites_are_refused(app):
    client = TestClient(app, base_url="http://localhost:7860")
    r = client.get("/api/status", headers={"Origin": "https://evil.example"})
    assert r.status_code == 403 and "this computer" in r.json()["detail"]
    assert client.post("/api/resume", headers={"Origin": "https://evil.example"}, json={}).status_code == 403


def test_dns_rebinding_is_refused(app):
    # A page on evil.example that resolves to 127.0.0.1 is same-origin, so its GETs carry no Origin header.
    assert TestClient(app, base_url="http://evil.example:7860").get("/api/status").status_code == 403


def test_allowed_origins_add_hosts(app, monkeypatch):
    monkeypatch.setenv("PIPECAT_ALLOWED_ORIGINS", "http://192.168.1.5:7860, https://box.lan")
    assert server.allowed_hosts() == {"localhost", "127.0.0.1", "::1", "192.168.1.5", "box.lan"}
    client = TestClient(app, base_url="http://192.168.1.5:7860")
    assert client.get("/api/status", headers={"Origin": "http://192.168.1.5:7860"}).status_code == 200


def test_report_markdown_shows_html_as_text():
    out = server._render_markdown(
        "**Bugs**\n1. <img src=x onerror=alert(1)> in vector<int>\n\n```cpp\n#include <vector>\n```\n\n"
        "| a |\n|---|\n| <b>x</b> |")
    assert "<img" not in out and "&lt;img src=x onerror=alert(1)&gt;" in out
    assert "vector&lt;int&gt;" in out
    assert "#include &lt;vector&gt;" in out and "&amp;lt;" not in out  # code is escaped once, not twice
    assert "<li>" in out and "<td>&lt;b&gt;x&lt;/b&gt;</td>" in out
