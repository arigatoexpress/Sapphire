variable "placeholder_image" {
  description = "A placeholder container image to deploy."
  type        = string
  default     = "gcr.io/cloud-run/hello"
}

resource "google_cloud_run_v2_service" "cloud_trader" {
  name     = "cloud-trader"
  location = var.region
  project  = var.project_id
  ingress  = "INGRESS_TRAFFIC_ALL"

  depends_on = [
    google_project_service.project_services["artifactregistry.googleapis.com"]
  ]

  template {
    service_account = google_service_account.main.email
    containers {
      image = var.placeholder_image
      ports {
        container_port = 8080
      }

      env {
        name  = "ENABLE_PAPER_TRADING"
        value = "false"
      }
    }

    # Temporarily disabled VPC access
    # vpc_access {
    #   connector = google_vpc_access_connector.main.id
    #   egress    = "ALL_TRAFFIC"
    # }
  }
}

resource "google_cloud_run_v2_service" "wallet_orchestrator" {
  name     = "wallet-orchestrator"
  location = var.region
  project  = var.project_id
  ingress  = "INGRESS_TRAFFIC_ALL"

  depends_on = [
    google_project_service.project_services["artifactregistry.googleapis.com"]
  ]

  template {
    service_account = google_service_account.main.email
    containers {
      image = var.placeholder_image
      ports {
        container_port = 8080
      }
    }

    # Temporarily disabled VPC access
    # vpc_access {
    #   connector = google_vpc_access_connector.main.id
    #   egress    = "ALL_TRAFFIC"
    # }
  }
}
