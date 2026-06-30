"""Observability layer for the M10 backend.

This module is where you (the learner) declare the three Prometheus metric
families and implement the three ASGI middleware classes that the autograder
exercises through the FastAPI app.

What lives here, and why:

  - Three metric families. A counter for request volume by (path, status), a
    histogram for request latency by path, and a gauge for in-flight requests.
    Together they answer "how much traffic, how slow, how concurrent."

  - Three middlewares. A request-id layer that attaches a per-request
    correlation id to the response and to the logging context. A
    structured-logging layer that emits one JSON line per response. A metrics
    layer that increments the counter, observes the latency histogram, and
    brackets the request with the in-flight gauge.

  Ordering matters: request-id is outermost (so it wraps the logging line),
  logging is middle, metrics is innermost (closest to the route).

Where to put what:

  - Declarations at MODULE SCOPE. If you declare a Counter / Histogram / Gauge
    inside a function or inside a middleware __call__, you will hit
    `Duplicated timeseries in CollectorRegistry` on the second request --
    every request re-runs the function. Module scope means the registry sees
    the declaration once at import time.

  - Label cardinality matters. The Lab's `requests_total` Counter uses
    exactly two labels: {path, status}. Do NOT add user-id, query-text,
    full-URL, or any other unbounded label.

Methodology pointers:

  - Reading sections 6-10 cover middleware, metric types, label cardinality.
  - See Common Pitfalls #1-#4 in the lab guide.
"""
from __future__ import annotations

import contextvars
import json
import logging
import time
import uuid

from prometheus_client import Counter, Gauge, Histogram
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id",
    default="",
)

requests_total = Counter(
    "requests_total",
    "Total HTTP requests by path and status.",
    ["path", "status"],
)

request_latency_seconds = Histogram(
    "request_latency_seconds",
    "HTTP request latency in seconds by path.",
    ["path"],
)

inflight_requests = Gauge(
    "inflight_requests",
    "Number of HTTP requests currently in flight.",
)


def _path_label(request: Request) -> str:
    route = request.scope.get("route")
    if route is not None and getattr(route, "path", None):
        return route.path
    return request.url.path


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = uuid.uuid4().hex
        token = request_id_var.set(request_id)

        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            request_id_var.reset(token)


class StructuredLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        latency_ms = (time.perf_counter() - start) * 1000

        log_record = {
            "ts": time.time(),
            "level": "INFO",
            "request_id": request_id_var.get(),
            "path": _path_label(request),
            "status": response.status_code,
            "latency_ms": round(latency_ms, 3),
        }

        logging.getLogger("m11.api").info(json.dumps(log_record))
        return response


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        inflight_requests.inc()
        start = time.perf_counter()

        try:
            response = await call_next(request)
        finally:
            inflight_requests.dec()

        elapsed = time.perf_counter() - start
        path = _path_label(request)
        status = str(response.status_code)

        requests_total.labels(path=path, status=status).inc()
        request_latency_seconds.labels(path=path).observe(elapsed)

        return response