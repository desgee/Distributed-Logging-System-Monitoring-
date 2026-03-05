# Distributed Logging System & Monitoring

A full observability stack built with FastAPI, Prometheus, Loki, Promtail, Grafana and Alertmanager with Slack alerting.

## Stack
- **FastAPI** — Demo app producing all observability signals
- **Prometheus** — Metrics collection and alerting rules
- **Loki** — Log aggregation and storage
- **Promtail** — Log collector that ships logs to Loki
- **Grafana** — Dashboard visualisation
- **Alertmanager** — Routes alerts to Slack

## Observability Signals
- CPU Usage
- Memory Usage
- Request Throughput
- P95 Latency
- Error Logs
- Failure Rate

## Prerequisites
- Docker
- Docker Compose

Kindly find below the documentation for the key steps to create a distributed logging and monitoring system.
https://www.notion.so/Distributed-Logging-System-Design-Monitoring-Pipeline-with-Loki-Prometheus-and-Grafana-3190ceb381a38071bcc1d764bc3a4a46?source=copy_link
