resource "google_redis_instance" "cache" {
  name             = "aster-redis-cache"
  tier             = "BASIC"
  memory_size_gb   = 1

  location_id           = "us-east1-b"
  authorized_network    = google_compute_network.main.id
  connect_mode          = "DIRECT_PEERING"
  transit_encryption_mode = "SERVER_AUTHENTICATION"

  depends_on = [google_project_service.project_services]
}
