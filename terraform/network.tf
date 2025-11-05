resource "google_compute_network" "main" {
  name                    = "aster-network-v2"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "main" {
  name          = "aster-subnet-v2"
  ip_cidr_range = "10.0.0.0/24"
  network       = google_compute_network.main.id
  region        = var.region
}

resource "google_vpc_access_connector" "main" {
  name           = "aster-vpc-connector"
  region         = var.region
  ip_cidr_range  = "10.8.0.0/28"
  network        = google_compute_network.main.id
  min_throughput = 200
  max_throughput = 300
}

resource "google_compute_router" "main" {
  name    = "aster-router"
  region  = var.region
  network = google_compute_network.main.id
}

resource "google_compute_router_nat" "main" {
  name                               = "aster-nat"
  router                             = google_compute_router.main.name
  region                             = google_compute_router.main.region
  source_subnetwork_ip_ranges_to_nat = "ALL_SUBNETWORKS_ALL_IP_RANGES"
  nat_ip_allocate_option             = "AUTO_ONLY"
}
