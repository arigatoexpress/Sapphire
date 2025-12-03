# Cloud Trader
resource "google_cloud_run_v2_service" "sapphire_cloud_trader" {
  name     = "sapphire-cloud-trader"
  location = var.region
  project  = var.project_id
  ingress  = "INGRESS_TRAFFIC_ALL"
  deletion_protection = false

  template {
    service_account = google_service_account.main.email
    
    scaling {
      min_instance_count = 1
      max_instance_count = 10
    }

    containers {
      image = "${var.region}-docker.pkg.dev/${var.project_id}/sapphire-repo/cloud-trader:latest"
      
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
resource "google_cloud_run_v2_service" "sapphire_hyperliquid_trader" {
  name                = "sapphire-hyperliquid-trader"
  location            = "northamerica-northeast1"
  project             = var.project_id
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = false

  template {
    service_account = google_service_account.main.email

    scaling {
      min_instance_count = 1
      max_instance_count = 10
    }
    
    vpc_access {
      connector = google_vpc_access_connector.sapphire_connector_ca.id
      egress    = "ALL_TRAFFIC"
    }

    containers {
      image = "${var.region}-docker.pkg.dev/${var.project_id}/sapphire-repo/hyperliquid-trader:latest"
      
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

# Dashboard
resource "google_cloud_run_v2_service" "sapphire_dashboard" {
  name     = "sapphire-dashboard"
  location = var.region
  project  = var.project_id
  ingress  = "INGRESS_TRAFFIC_ALL"
  deletion_protection = false

  template {
    service_account = google_service_account.main.email
    
    containers {
      image = "${var.region}-docker.pkg.dev/${var.project_id}/sapphire-repo/dashboard:latest"
      
      ports {
        container_port = 3000
      }
      
      env {
        name  = "VITE_API_URL"
        value = google_cloud_run_v2_service.sapphire_cloud_trader.uri
      }
    }
  }
}

# Public Access for Cloud Trader
resource "google_cloud_run_service_iam_member" "public_access_cloud_trader" {
  location = google_cloud_run_v2_service.sapphire_cloud_trader.location
  project  = google_cloud_run_v2_service.sapphire_cloud_trader.project
  service  = google_cloud_run_v2_service.sapphire_cloud_trader.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# Public Access for Dashboard
resource "google_cloud_run_service_iam_member" "public_access_dashboard" {
  location = google_cloud_run_v2_service.sapphire_dashboard.location
  project  = google_cloud_run_v2_service.sapphire_dashboard.project
  service  = google_cloud_run_v2_service.sapphire_dashboard.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
