resource "google_project_service" "project_services" {
  for_each = toset([
    "run.googleapis.com",
    "redis.googleapis.com",
    "pubsub.googleapis.com",
    "iam.googleapis.com",
    "aiplatform.googleapis.com",
    "artifactregistry.googleapis.com",
    "cloudbuild.googleapis.com",
    "compute.googleapis.com",
    "vpcaccess.googleapis.com",
    "secretmanager.googleapis.com",
    "sqladmin.googleapis.com",
    "servicenetworking.googleapis.com",
  ])

  service                    = each.key
  project                    = var.project_id
  disable_dependent_services = true
  disable_on_destroy         = false
}

resource "google_service_account" "main" {
  project      = var.project_id
  account_id   = "sapphire-main-sa"
  display_name = "Sapphire Main Service Account"
}
