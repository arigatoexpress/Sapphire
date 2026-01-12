# Cloud Trader
resource "google_cloud_run_v2_service" "sapphire_cloud_trader" {
  name     = "sapphire-cloud-trader"
  location = var.region
  project  = var.project_id
  ingress  = "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER"  # SECURITY: Restrict to internal + LB only
  deletion_protection = false

  template {
    service_account = google_service_account.main.email

    scaling {
      min_instance_count = 1
      max_instance_count = 10
    }

    # SECURITY: Enable gVisor sandboxing for kernel hardening
    execution_environment = "EXECUTION_ENVIRONMENT_GEN2"

    containers {
      image = "gcr.io/${var.project_id}/cloud-trader:backend"

      env {
        name  = "DATABASE_URL"
        value = "postgresql://trading_user:changeme123@${google_sql_database_instance.sapphire_db.private_ip_address}:5432/trading_db"
      }
      env {
        name  = "REDIS_URL"
        value = "redis://${google_redis_instance.sapphire_cache.host}:${google_redis_instance.sapphire_cache.port}"
      }

      env {
        name = "GROK_API_KEY"
        value_source {
          secret_key_ref {
            secret = google_secret_manager_secret.secrets["GROK_API_KEY"].secret_id
            version = "latest"
          }
        }
      }
      env {
        name = "ASTER_API_KEY"
        value_source {
          secret_key_ref {
            secret = google_secret_manager_secret.secrets["ASTER_API_KEY"].secret_id
            version = "latest"
          }
        }
      }
      env {
        name = "ASTER_SECRET_KEY"
        value_source {
          secret_key_ref {
            secret = google_secret_manager_secret.secrets["ASTER_SECRET_KEY"].secret_id
            version = "latest"
          }
        }
      }
      env {
        name = "TELEGRAM_BOT_TOKEN"
        value_source {
          secret_key_ref {
            secret = "TELEGRAM_BOT_TOKEN"
            version = "latest"
          }
        }
      }
      env {
        name = "TELEGRAM_CHAT_ID"
        value_source {
          secret_key_ref {
            secret = "TELEGRAM_CHAT_ID"
            version = "latest"
          }
        }
      }
    }

    vpc_access {
      connector = google_vpc_access_connector.sapphire_connector.id
      egress    = "ALL_TRAFFIC"
    }
  }
}

# Hyperliquid Trader
# Hyperliquid Trader
resource "google_cloud_run_v2_service" "sapphire_hyperliquid_trader" {
  name                = "sapphire-hyperliquid-trader"
  location            = var.region
  project             = var.project_id
  ingress             = "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER"  # SECURITY: Restrict to internal + LB only
  deletion_protection = false

  template {
    service_account = google_service_account.main.email

    scaling {
      min_instance_count = 1
      max_instance_count = 10
    }

    # SECURITY: Enable gVisor sandboxing for kernel hardening
    execution_environment = "EXECUTION_ENVIRONMENT_GEN2"

    vpc_access {
      connector = google_vpc_access_connector.sapphire_connector.id
      egress    = "ALL_TRAFFIC"
    }

    containers {
      image = "gcr.io/${var.project_id}/hyperliquid-trader:latest"

      resources {
        limits = {
          cpu    = "1000m"
          memory = "512Mi"
        }
        cpu_idle = false # Always on CPU for HFT
      }

      ports {
        container_port = 8080
      }

      env {
        name = "REDIS_URL"
        # Redis is in us-east1. Access via private IP is possible because VPC is global.
        # Latency might be slightly higher (~10-20ms) but acceptable for cache.
        value = "redis://${google_redis_instance.sapphire_cache.host}:${google_redis_instance.sapphire_cache.port}/0"
      }

      env {
        name = "GEMINI_API_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.secrets["GEMINI_API_KEY"].secret_id
            version = "latest"
          }
        }
      }

      env {
        name = "HL_SECRET_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.secrets["HL_SECRET_KEY"].secret_id
            version = "latest"
          }
        }
      }

      env {
        name = "GROK_API_KEY"
        value_source {
          secret_key_ref {
            secret = google_secret_manager_secret.secrets["GROK_API_KEY"].secret_id
            version = "latest"
          }
        }
      }

      env {
        name = "TELEGRAM_BOT_TOKEN"
        value_source {
          secret_key_ref {
            secret = "TELEGRAM_BOT_TOKEN"
            version = "latest"
          }
        }
      }
      env {
        name = "TELEGRAM_CHAT_ID"
        value_source {
          secret_key_ref {
            secret = "TELEGRAM_CHAT_ID"
            version = "latest"
          }
        }
      }
    }
  }
}



# SECURITY: Removed allUsers public access
# Access is now restricted to authenticated service accounts only
resource "google_cloud_run_service_iam_member" "sa_access_cloud_trader" {
  location = google_cloud_run_v2_service.sapphire_cloud_trader.location
  project  = google_cloud_run_v2_service.sapphire_cloud_trader.project
  service  = google_cloud_run_v2_service.sapphire_cloud_trader.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.main.email}"
}
