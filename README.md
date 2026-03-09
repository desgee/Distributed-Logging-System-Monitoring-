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

# NB: Monitoring/alertmanager.yml
The alertmanager.yml was not pushed to github because it contains my personal slack webhook url.

Create the Monitoring/alertmanager.yml and include your slack webhook url

```python
global:
  resolve_timeout: 5m
  slack_api_url: "YOUR_ACTUAL_WEBHOOK_URL"

route:
  group_by: ["alertname"]
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 1h
  receiver: "slack-alerts"

receivers:
  - name: "slack-alerts"
    slack_configs:
      - channel: "#alerts"
        send_resolved: true
        title: '{{ if eq .Status "firing" }}🔴 ALERT{{ else }}✅ RESOLVED{{ end }}: {{ .GroupLabels.alertname }}'
        text: |
          {{ range .Alerts }}
          *Status:*    {{ .Status | toUpper }}
          *Alert:*     {{ .Annotations.summary }}
          *Details:*   {{ .Annotations.description }}
          *Severity:*  {{ .Labels.severity }}
          {{ end }}

```




Kindly find below the documentation for the key steps to create a distributed logging and monitoring system.
https://www.notion.so/Distributed-Logging-System-Design-Monitoring-Pipeline-with-Loki-Prometheus-and-Grafana-3190ceb381a38071bcc1d764bc3a4a46?source=copy_link
