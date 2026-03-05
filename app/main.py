"""
NexCell Demo FastAPI Application
Monitoring: Prometheus + Loki (via Promtail) + Grafana
Signals:    CPU, Memory, Throughput, P95 Latency, Error Logs, Failure Rate
"""

import asyncio
import json
import logging
import random
import sys
import time
from contextlib import asynccontextmanager
from datetime import datetime

import psutil
import uvicorn
from fastapi import FastAPI, HTTPException, Request, Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

# ─── Structured JSON Logger ────────────────────────────────────────────────────
# Every log line is a JSON object written to stdout.
# Promtail reads stdout, parses the JSON, and ships it to Loki.

SKIP_FIELDS = {
    "msg", "args", "levelname", "levelno", "pathname", "filename",
    "module", "exc_info", "exc_text", "stack_info", "lineno",
    "funcName", "created", "msecs", "relativeCreated", "thread",
    "threadName", "processName", "process", "name", "message",
}


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        obj = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level":     record.levelname,
            "logger":    record.name,
            "message":   record.getMessage(),
            "module":    record.module,
            "function":  record.funcName,
            "line":      record.lineno,
        }
        obj.update({k: v for k, v in record.__dict__.items() if k not in SKIP_FIELDS})
        if record.exc_info:
            obj["exception"] = self.formatException(record.exc_info)
        return json.dumps(obj)


def get_logger(name: str) -> logging.Logger:
    log = logging.getLogger(name)
    log.setLevel(logging.DEBUG)
    if not log.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JSONFormatter())
        log.addHandler(handler)
    log.propagate = False
    return log


logger = get_logger("nexcell")


# ─── Prometheus Metrics ────────────────────────────────────────────────────────

REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "http_status"],
)

REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0],
)

ERROR_COUNT = Counter(
    "http_errors_total",
    "Total HTTP 4xx and 5xx errors",
    ["method", "endpoint", "http_status"],
)

CPU_GAUGE   = Gauge("system_cpu_usage_percent",    "CPU usage as a percentage")
MEM_BYTES   = Gauge("system_memory_usage_bytes",   "Memory used in bytes")
MEM_PCT     = Gauge("system_memory_usage_percent", "Memory used as a percentage")
ACTIVE_REQS = Gauge("http_active_requests",        "Current in-flight request count")


# ─── Background Task ───────────────────────────────────────────────────────────
# Updates CPU and Memory gauges every 5 seconds

async def collect_system_metrics() -> None:
    while True:
        try:
            cpu = psutil.cpu_percent(interval=1)
            mem = psutil.virtual_memory()
            CPU_GAUGE.set(cpu)
            MEM_BYTES.set(mem.used)
            MEM_PCT.set(mem.percent)
            logger.debug("system_metrics_collected", extra={
                "cpu_percent":    cpu,
                "memory_percent": mem.percent,
            })
        except Exception as exc:
            logger.error("system_metrics_failed", extra={"error": str(exc)})
        await asyncio.sleep(5)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("startup", extra={"event": "startup"})
    task = asyncio.create_task(collect_system_metrics())
    yield
    task.cancel()
    logger.info("shutdown", extra={"event": "shutdown"})


# ─── App Instance ──────────────────────────────────────────────────────────────

app = FastAPI(
    title="NexCell Monitoring Demo",
    version="1.0.0",
    lifespan=lifespan,
)


# ─── Middleware ────────────────────────────────────────────────────────────────
# Runs on every request — records latency, throughput, and errors

@app.middleware("http")
async def observability_middleware(request: Request, call_next):
    start    = time.perf_counter()
    endpoint = request.url.path
    ACTIVE_REQS.inc()

    try:
        response = await call_next(request)
    except Exception as exc:
        duration = time.perf_counter() - start
        ACTIVE_REQS.dec()
        REQUEST_COUNT.labels(request.method, endpoint, 500).inc()
        REQUEST_LATENCY.labels(request.method, endpoint).observe(duration)
        ERROR_COUNT.labels(request.method, endpoint, 500).inc()
        logger.error("request_unhandled_exception", extra={
            "method":      request.method,
            "endpoint":    endpoint,
            "status_code": 500,
            "duration_ms": round(duration * 1000, 2),
            "error":       str(exc),
        })
        raise

    duration = time.perf_counter() - start
    ACTIVE_REQS.dec()
    status = response.status_code

    REQUEST_COUNT.labels(request.method, endpoint, status).inc()
    REQUEST_LATENCY.labels(request.method, endpoint).observe(duration)

    log_extra = {
        "method":      request.method,
        "endpoint":    endpoint,
        "status_code": status,
        "duration_ms": round(duration * 1000, 2),
    }

    if status >= 500:
        ERROR_COUNT.labels(request.method, endpoint, status).inc()
        logger.error("request_completed", extra=log_extra)
    elif status >= 400:
        ERROR_COUNT.labels(request.method, endpoint, status).inc()
        logger.warning("request_completed", extra=log_extra)
    else:
        logger.info("request_completed", extra=log_extra)

    return response


# ─── Routes ───────────────────────────────────────────────────────────────────

@app.get("/", tags=["Health"])
async def root():
    return {"status": "ok", "service": "nexcell-monitoring-demo"}


@app.get("/health", tags=["Health"])
async def health():
    mem = psutil.virtual_memory()
    return {
        "status":         "healthy",
        "cpu_percent":    psutil.cpu_percent(),
        "memory_percent": mem.percent,
        "timestamp":      datetime.utcnow().isoformat() + "Z",
    }


@app.get("/metrics", tags=["Observability"])
async def metrics():
    """Prometheus scrapes this endpoint every 5 seconds."""
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/api/orders", tags=["Business"])
async def list_orders():
    await asyncio.sleep(random.uniform(0.01, 0.3))
    orders = [
        {"id": i, "status": random.choice(["pending", "shipped", "delivered"])}
        for i in range(1, 11)
    ]
    logger.info("orders_listed", extra={"count": len(orders)})
    return {"orders": orders, "count": len(orders)}


@app.get("/api/orders/{order_id}", tags=["Business"])
async def get_order(order_id: int):
    await asyncio.sleep(random.uniform(0.005, 0.2))
    roll = random.random()
    if roll < 0.05:
        logger.error("order_db_timeout", extra={
            "order_id": order_id, "error_type": "db_timeout"
        })
        raise HTTPException(status_code=500, detail="Database timeout")
    if roll < 0.15:
        logger.warning("order_not_found", extra={"order_id": order_id})
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found")
    logger.info("order_fetched", extra={"order_id": order_id})
    return {"id": order_id, "status": "shipped", "items": random.randint(1, 5)}


@app.post("/api/orders", tags=["Business"])
async def create_order():
    await asyncio.sleep(random.uniform(0.05, 0.4))
    if random.random() < 0.08:
        logger.error("order_create_failed", extra={"error_type": "validation_error"})
        raise HTTPException(status_code=422, detail="Order validation failed")
    order_id = random.randint(1000, 9999)
    logger.info("order_created", extra={"order_id": order_id})
    return {"id": order_id, "status": "pending"}


@app.get("/api/slow", tags=["Simulation"])
async def slow_endpoint():
    """Always 0.8–2.5s — drives P95 latency panel."""
    delay = random.uniform(0.8, 2.5)
    await asyncio.sleep(delay)
    logger.warning("slow_response", extra={"delay_ms": round(delay * 1000, 2)})
    return {"message": "slow but successful", "delay_ms": round(delay * 1000, 2)}


@app.get("/api/error", tags=["Simulation"])
async def force_error():
    """Always 500 — drives failure rate and error log panels."""
    logger.error("forced_error", extra={"error_type": "intentional"})
    raise HTTPException(status_code=500, detail="Intentional error for demo")


@app.get("/api/cpu-spike", tags=["Simulation"])
async def cpu_spike():
    """Burns CPU for 5 seconds across multiple loops."""
    logger.warning("cpu_spike_started")
    start = time.perf_counter()
    # Run for 5 seconds instead of 2
    while time.perf_counter() - start < 5.0:
        # More intensive computation
        _ = [i * i * i for i in range(50_000)]
    ms = round((time.perf_counter() - start) * 1000, 2)
    logger.warning("cpu_spike_ended", extra={"duration_ms": ms})
    return {"message": "CPU spike complete", "duration_ms": ms}


@app.get("/api/memory-spike", tags=["Simulation"])
async def memory_spike():
    """Holds ~80 MB for 1 second — drives memory panel."""
    logger.warning("memory_spike_started")
    big = [0] * (10 * 1024 * 1024)
    await asyncio.sleep(1.0)
    del big
    logger.warning("memory_spike_ended")
    return {"message": "Memory spike complete"}


@app.get("/api/load", tags=["Simulation"])
async def generate_load():
    """Fires 50 concurrent coroutines — fills throughput and latency panels fast."""
    logger.info("load_started", extra={"requests": 50})
    await asyncio.gather(
        *[asyncio.sleep(random.uniform(0.01, 0.4)) for _ in range(50)]
    )
    logger.info("load_ended")
    return {"message": "Load generated", "simulated_requests": 50}
