"""Operational telemetry per OPS-06.

Per-RPC counters + latency histograms exposed at /metrics in Prometheus
format. Standard metric names mirror OpenTelemetry semantic conventions
so any OTel-compatible scraper (DataDog, Grafana, New Relic) works.

Cardinality control (per D-014): consumer dimension is `consumer_type`
(3 values), never `caller_id` (unbounded). Distinct from the per-call
audit log (SEC-02) which carries caller_id for compliance.
"""

from __future__ import annotations

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)


def build_registry() -> tuple[CollectorRegistry, Metrics]:
    """Return a fresh registry + bound Metrics object.

    Per-app rather than module-global so tests can build isolated registries.
    """
    registry = CollectorRegistry()
    metrics = Metrics(registry)
    return registry, metrics


class Metrics:
    def __init__(self, registry: CollectorRegistry) -> None:
        self.requests_total = Counter(
            "connector_rpc_requests_total",
            "Total RPC calls processed.",
            labelnames=("rpc", "consumer_type", "status"),
            registry=registry,
        )
        self.latency_seconds = Histogram(
            "connector_rpc_latency_seconds",
            "RPC end-to-end latency (auth + handler + Metabase + reshape).",
            labelnames=("rpc", "consumer_type"),
            buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
            registry=registry,
        )
        self.audit_writes_total = Counter(
            "connector_audit_writes_total",
            "Audit records written.",
            labelnames=("status",),
            registry=registry,
        )
        self.circuit_breaker_state = Gauge(
            "connector_circuit_breaker_state",
            "Metabase circuit-breaker state (0=closed, 1=open, 2=half-open).",
            registry=registry,
        )

    def render(self, registry: CollectorRegistry) -> tuple[bytes, str]:
        return generate_latest(registry), CONTENT_TYPE_LATEST
