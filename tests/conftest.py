import os
import sys
import tempfile
from datetime import timedelta

import pytest
import requests

# Never touch the real leads.db, even when app.py runs init_db() on import.
os.environ["HUSTLEHUB_DB"] = os.path.join(tempfile.gettempdir(), "hustlehubm-test.db")

# Make the project folder importable from the tests.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """A fresh, empty database for each test."""
    import database

    path = str(tmp_path / "test.db")
    monkeypatch.setattr(database, "DATABASE", path)
    database.init_db()
    return path


class FakeResponse:
    def __init__(self, html, url, status_code=200, seconds=0.5):
        self.content = html.encode("utf-8")
        self.text = html
        self.url = url
        self.status_code = status_code
        self.headers = {}
        self.elapsed = timedelta(seconds=seconds)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


@pytest.fixture
def fake_site(monkeypatch):
    """Serve fixed HTML instead of going to the internet.

    fake_site({"https://example.co.za/": "<html>...</html>"})
    """
    import website_analyzer

    def install(pages, default_status=404):
        def fake_get(url, **kwargs):
            if url in pages:
                return FakeResponse(pages[url], url=url)
            return FakeResponse("", url=url, status_code=default_status)

        monkeypatch.setattr(website_analyzer.requests, "get", fake_get)

    return install
