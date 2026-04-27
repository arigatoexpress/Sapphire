# Network
resource "google_compute_network" "sapphire_net" {
  name                    = "sapphire-net"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "sapphire_subnet" {
  name          = "sapphire-subnet"
  ip_cidr_range = "10.1.0.0/24"
  network       = google_compute_network.sapphire_net.id
  region        = var.region
}

# Private Service Access for Cloud SQL
resource "google_compute_global_address" "private_ip_address" {
  name          = "sapphire-private-ip"
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = 16
  network       = google_compute_network.sapphire_net.id
}

resource "google_service_networking_connection" "private_vpc_connection" {
  network                 = google_compute_network.sapphire_net.id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.private_ip_address.name]
}

# Cloud NAT for Internet Access
resource "google_compute_router" "sapphire_router" {
  name    = "sapphire-router"
  network = google_compute_network.sapphire_net.name
  region  = var.region
}

# Static IP for Cloud NAT
resource "google_compute_address" "sapphire_nat_ip" {
  name   = "sapphire-nat-ip"
  region = var.region
}

resource "google_compute_router_nat" "sapphire_nat" {
  name                               = "sapphire-nat"
  router                             = google_compute_router.sapphire_router.name
  region                             = google_compute_router.sapphire_router.region
  nat_ip_allocate_option             = "MANUAL_ONLY"
  nat_ips                            = [google_compute_address.sapphire_nat_ip.self_link]
  source_subnetwork_ip_ranges_to_nat = "ALL_SUBNETWORKS_ALL_IP_RANGES"
}

resource "google_vpc_access_connector" "sapphire_connector" {
  name           = "sapphire-conn"
  region         = var.region
  ip_cidr_range  = "10.8.1.0/28"
  network        = google_compute_network.sapphire_net.id
  min_throughput = 200
  max_throughput = 300
}

# Output the static IP
output "static_nat_ip" {
  value       = google_compute_address.sapphire_nat_ip.address
  description = "Static IP address for NAT gateway - whitelist this on Aster exchange"
}

# Database (Cloud SQL)
resource "google_sql_database_instance" "sapphire_db" {
  name             = "sapphire-db-${random_id.db_suffix.hex}"
  database_version = "POSTGRES_15"
  region           = var.region

  depends_on = [google_service_networking_connection.private_vpc_connection]

  settings {
    tier = "db-f1-micro"
    ip_configuration {
      ipv4_enabled    = true
      private_network = google_compute_network.sapphire_net.id
    }
  }
  deletion_protection = false # For easier cleanup during testing
}

resource "random_id" "db_suffix" {
  byte_length = 4
}

resource "google_sql_database" "trading_db" {
  name     = "trading_db"
  instance = google_sql_database_instance.sapphire_db.name
}

resource "google_sql_user" "trading_user" {
  name     = "trading_user"
  instance = google_sql_database_instance.sapphire_db.name
  password = var.trading_db_password
}

# Redis
resource "google_redis_instance" "sapphire_cache" {
  name           = "sapphire-cache"
  tier           = "BASIC"
  memory_size_gb = 1
  location_id    = "${var.region}-b"

  authorized_network = google_compute_network.sapphire_net.id
  connect_mode       = "DIRECT_PEERING"
}

# Artifact Registry
resource "google_artifact_registry_repository" "sapphire_repo" {
  location      = var.region
  repository_id = "sapphire-repo"
  description   = "Docker repository for Sapphire AI 2.0"
  format        = "DOCKER"
}

# Secrets (Placeholders)
resource "google_secret_manager_secret" "secrets" {
  for_each  = toset(["HL_SECRET_KEY", "ASTER_SECRET_KEY", "GROK_API_KEY", "GEMINI_API_KEY", "ASTER_API_KEY"])
  project   = var.project_id
  secret_id = each.key
  replication {
    auto {}
  }
}

# History Bucket
resource "google_storage_bucket" "sapphire_history" {
  name          = "sapphire-history-${random_id.db_suffix.hex}"
  location      = var.region
  force_destroy = true

  uniform_bucket_level_access = true
}

# Cloud DNS
resource "google_dns_managed_zone" "sapphire_zone" {
  name        = "sapphire-zone"
  dns_name    = "sapphiretrade.xyz."
  description = "Zone for sapphiretrade.xyz"
  visibility  = "public"
}

# Enable APIs
resource "google_project_service" "firebase" {
  service = "firebase.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "firebase_hosting" {
  service = "firebasehosting.googleapis.com"
  disable_on_destroy = false
}

# Agent Aster Pub/Sub
resource "google_pubsub_topic" "aster_strategy" {
  name = "aster-strategy"
}

resource "google_pubsub_topic" "aster_execution" {
  name = "aster-execution"
}

# Subscriptions
resource "google_pubsub_subscription" "aster_strategy_sub" {
  name  = "aster-strategy-sub"
  topic = google_pubsub_topic.aster_strategy.name
}

resource "google_pubsub_subscription" "lighter_strategy_sub" {
  name  = "lighter-strategy-sub"
  topic = google_pubsub_topic.aster_strategy.name
}

resource "google_pubsub_subscription" "dashboard_execution_sub" {
  name  = "dashboard-execution-sub"
  topic = google_pubsub_topic.aster_execution.name
}
