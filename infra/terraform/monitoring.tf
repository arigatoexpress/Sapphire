# ==============================================================================
# MONITORING.TF - Cloud Logging, Monitoring, and Alerts
# ==============================================================================

# Enable Cloud Monitoring API
resource "google_project_service" "monitoring" {
  service            = "monitoring.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "logging" {
  service            = "logging.googleapis.com"
  disable_on_destroy = false
}

# Notification Channel - Email
resource "google_monitoring_notification_channel" "email" {
  display_name = "Sapphire Trading Alerts"
  type         = "email"
  labels = {
    email_address = var.alert_email
  }
}

# Alert Policy - High Error Rate
resource "google_monitoring_alert_policy" "high_error_rate" {
  display_name = "Sapphire High Error Rate"
  combiner     = "OR"

  conditions {
    display_name = "Error rate > 5%"
    condition_threshold {
      filter          = "resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"sapphire-cloud-trader\" AND metric.type=\"run.googleapis.com/request_count\" AND metric.labels.response_code_class=\"5xx\""
      comparison      = "COMPARISON_GT"
      threshold_value = 0.05
      duration        = "300s"
      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_RATE"
      }
    }
  }

  notification_channels = [google_monitoring_notification_channel.email.name]

  alert_strategy {
    auto_close = "1800s"
  }
}

# Alert Policy - High Latency
resource "google_monitoring_alert_policy" "high_latency" {
  display_name = "Sapphire High Latency"
  combiner     = "OR"

  conditions {
    display_name = "Latency > 5s"
    condition_threshold {
      filter          = "resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"sapphire-cloud-trader\" AND metric.type=\"run.googleapis.com/request_latencies\""
      comparison      = "COMPARISON_GT"
      threshold_value = 5000  # 5 seconds in ms
      duration        = "300s"
      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_PERCENTILE_99"
      }
    }
  }

  notification_channels = [google_monitoring_notification_channel.email.name]
}

# Alert Policy - Max Drawdown Reached
resource "google_monitoring_alert_policy" "drawdown_alert" {
  display_name = "Sapphire Max Drawdown"
  combiner     = "OR"

  conditions {
    display_name = "Drawdown > 15%"
    condition_threshold {
      filter          = "resource.type=\"cloud_run_revision\" AND metric.type=\"logging.googleapis.com/user/sapphire_drawdown\""
      comparison      = "COMPARISON_GT"
      threshold_value = 0.15
      duration        = "0s"
      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_MAX"
      }
    }
  }

  notification_channels = [google_monitoring_notification_channel.email.name]

  alert_strategy {
    auto_close = "86400s"  # 24 hours
  }
}

# Log Metric - Drawdown
resource "google_logging_metric" "drawdown" {
  name   = "sapphire_drawdown"
  filter = "resource.type=\"cloud_run_revision\" AND jsonPayload.metric_name=\"drawdown\""

  metric_descriptor {
    metric_kind = "GAUGE"
    value_type  = "DOUBLE"
    unit        = "1"
  }

  value_extractor = "EXTRACT(jsonPayload.value)"
}

# Log Metric - Win Rate
resource "google_logging_metric" "win_rate" {
  name   = "sapphire_win_rate"
  filter = "resource.type=\"cloud_run_revision\" AND jsonPayload.metric_name=\"win_rate\""

  metric_descriptor {
    metric_kind = "GAUGE"
    value_type  = "DOUBLE"
    unit        = "1"
  }

  value_extractor = "EXTRACT(jsonPayload.value)"
}

# Log Metric - Trade Count
resource "google_logging_metric" "trade_count" {
  name   = "sapphire_trades"
  filter = "resource.type=\"cloud_run_revision\" AND jsonPayload.event=\"trade_executed\""

  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
    unit        = "1"
  }
}

# Dashboard
resource "google_monitoring_dashboard" "sapphire" {
  dashboard_json = jsonencode({
    displayName = "Sapphire Trading Dashboard"
    mosaicLayout = {
      columns = 12
      tiles = [
        {
          width  = 6
          height = 4
          widget = {
            title = "Request Count"
            xyChart = {
              dataSets = [{
                timeSeriesQuery = {
                  timeSeriesFilter = {
                    filter = "resource.type=\"cloud_run_revision\" AND metric.type=\"run.googleapis.com/request_count\""
                  }
                }
              }]
            }
          }
        },
        {
          xPos   = 6
          width  = 6
          height = 4
          widget = {
            title = "Latency (p99)"
            xyChart = {
              dataSets = [{
                timeSeriesQuery = {
                  timeSeriesFilter = {
                    filter = "resource.type=\"cloud_run_revision\" AND metric.type=\"run.googleapis.com/request_latencies\""
                    aggregation = {
                      alignmentPeriod  = "60s"
                      perSeriesAligner = "ALIGN_PERCENTILE_99"
                    }
                  }
                }
              }]
            }
          }
        },
        {
          yPos   = 4
          width  = 4
          height = 4
          widget = {
            title = "Win Rate"
            scorecard = {
              timeSeriesQuery = {
                timeSeriesFilter = {
                  filter = "metric.type=\"logging.googleapis.com/user/sapphire_win_rate\""
                }
              }
              thresholds = [
                { value = 0.5, color = "YELLOW" },
                { value = 0.6, color = "GREEN" }
              ]
            }
          }
        },
        {
          yPos   = 4
          xPos   = 4
          width  = 4
          height = 4
          widget = {
            title = "Drawdown"
            scorecard = {
              timeSeriesQuery = {
                timeSeriesFilter = {
                  filter = "metric.type=\"logging.googleapis.com/user/sapphire_drawdown\""
                }
              }
              thresholds = [
                { value = 0.10, color = "YELLOW" },
                { value = 0.15, color = "RED" }
              ]
            }
          }
        },
        {
          yPos   = 4
          xPos   = 8
          width  = 4
          height = 4
          widget = {
            title = "Total Trades"
            scorecard = {
              timeSeriesQuery = {
                timeSeriesFilter = {
                  filter = "metric.type=\"logging.googleapis.com/user/sapphire_trades\""
                }
              }
            }
          }
        },
        {
          yPos   = 8
          width  = 12
          height = 4
          widget = {
            title = "PnL Over Time"
            xyChart = {
              dataSets = [{
                timeSeriesQuery = {
                  timeSeriesFilter = {
                    filter = "metric.type=\"logging.googleapis.com/user/sapphire_pnl\""
                  }
                }
              }]
            }
          }
        }
      ]
    }
  })
}

# Log Metric - PnL
resource "google_logging_metric" "pnl" {
  name   = "sapphire_pnl"
  filter = "resource.type=\"cloud_run_revision\" AND jsonPayload.metric_name=\"pnl\""

  metric_descriptor {
    metric_kind = "GAUGE"
    value_type  = "DOUBLE"
    unit        = "1"
  }

  value_extractor = "EXTRACT(jsonPayload.value)"
}

# Variable
variable "alert_email" {
  description = "Email for alerts"
  type        = string
  default     = "alerts@sapphiretrade.xyz"
}
