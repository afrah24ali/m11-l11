"""YOUR tests for the observability layer.

Per the lab guide, write at least 3 substantive tests, each with at least
1 assertion. The autograder enforces only the structure (3+ test functions,
each with an `assert` and a non-stub body); the specific behaviors you
choose to verify are up to you.

You name the tests, you decide what to assert, you choose the test
strategy (TestClient + header inspection? caplog + log parsing?
/metrics scrape + counter delta?). The placeholders below show one
possible split (one test per middleware), but you are free to pick any
three behaviors that exercise meaningful properties of your
instrumentation -- e.g. test that the request-id flows across two
sequential requests with distinct ids, test that the metrics counter
reflects a 500 response status correctly, test that the structured log
line carries the X-Request-ID matching the response header.

The autograder does not import your test function names; rename them
freely.
"""

import json
import logging

from fastapi.testclient import TestClient

from api.main import app
from api.observability import requests_total

def _counter_value(path: str, status: str) -> float:
    return requests_total.labels(path=path, status=status)._value.get()


def test_request_id_header_is_set_and_non_empty():
    client = TestClient(app)

    response = client.get("/healthz")

    assert response.status_code == 200
    assert "X-Request-ID" in response.headers
    assert response.headers["X-Request-ID"] != ""


def test_requests_total_counter_increments_after_request():
    client = TestClient(app)

    before = _counter_value("/healthz", "200")
    response = client.get("/healthz")
    after = _counter_value("/healthz", "200")

    assert response.status_code == 200
    assert after == before + 1


def test_structured_log_contains_matching_request_id(caplog):
    client = TestClient(app)

    with caplog.at_level(logging.INFO, logger="m11.api"):
        response = client.get("/healthz")

    request_id = response.headers["X-Request-ID"]

    parsed_logs = []
    for record in caplog.records:
        try:
            parsed_logs.append(json.loads(record.message))
        except json.JSONDecodeError:
            continue

    healthz_logs = [
        log for log in parsed_logs
        if log.get("path") == "/healthz"
    ]

    assert healthz_logs
    assert healthz_logs[-1]["request_id"] == request_id
    assert healthz_logs[-1]["status"] == 200
    assert "latency_ms" in healthz_logs[-1]