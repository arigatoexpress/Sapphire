# ==============================================================================
# SECURITY.TF - Cloud Armor WAF & Security Policies
# ==============================================================================

# Cloud Armor Security Policy - Rate Limiting & Geo-Fencing
resource "google_compute_security_policy" "sapphire_waf" {
  name        = "sapphire-waf-policy"
  description = "WAF rules for Sapphire Trading API"

  # Default rule - Allow traffic
  rule {
    action   = "allow"
    priority = "2147483647"  # Lowest priority (default)
    match {
      versioned_expr = "SRC_IPS_V1"
      config {
        src_ip_ranges = ["*"]
      }
    }
    description = "Default allow rule"
  }

  # Rate Limiting - 1000 requests per minute per IP
  rule {
    action   = "rate_based_ban"
    priority = "1000"
    match {
      versioned_expr = "SRC_IPS_V1"
      config {
        src_ip_ranges = ["*"]
      }
    }
    rate_limit_options {
      conform_action = "allow"
      exceed_action  = "deny(429)"
      enforce_on_key = "IP"
      rate_limit_threshold {
        count        = 1000
        interval_sec = 60
      }
      ban_duration_sec = 300  # 5 minute ban for abusers
    }
    description = "Rate limit: 1000 req/min per IP"
  }

  # Geo-Fencing - Allow US only (configurable via variable)
  rule {
    action   = "deny(403)"
    priority = "900"
    match {
      expr {
        expression = "origin.region_code != 'US' && origin.region_code != 'CA' && origin.region_code != 'GB'"
      }
    }
    description = "Geo-fence: Allow US, CA, GB only"
  }

  # Block Known Bad IPs (Example: Tor exit nodes would go here)
  rule {
    action   = "deny(403)"
    priority = "800"
    match {
      versioned_expr = "SRC_IPS_V1"
      config {
        src_ip_ranges = ["0.0.0.0/8"]  # Reserved addresses (placeholder)
      }
    }
    description = "Block reserved/invalid IP ranges"
  }

  # OWASP ModSecurity Core Rule Set - XSS/SQLi Protection
  rule {
    action   = "deny(403)"
    priority = "700"
    match {
      expr {
        expression = "evaluatePreconfiguredWaf('xss-v33-stable', {'sensitivity': 1})"
      }
    }
    description = "Block XSS attacks (OWASP CRS)"
  }

  rule {
    action   = "deny(403)"
    priority = "600"
    match {
      expr {
        expression = "evaluatePreconfiguredWaf('sqli-v33-stable', {'sensitivity': 1})"
      }
    }
    description = "Block SQL injection (OWASP CRS)"
  }
}

# Secret Manager IAM - Restrict to service account only
resource "google_secret_manager_secret_iam_member" "secret_access" {
  for_each  = toset(["HL_SECRET_KEY", "ASTER_SECRET_KEY", "GROK_API_KEY", "GEMINI_API_KEY", "ASTER_API_KEY"])
  project   = var.project_id
  secret_id = each.key
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.main.email}"
}

# Service Account - Least Privilege
resource "google_service_account" "main" {
  account_id   = "sapphire-trader-sa"
  display_name = "Sapphire Trader Service Account"
  description  = "Service account for Cloud Run services with least-privilege access"
}

# IAM Roles for Service Account
resource "google_project_iam_member" "sa_pubsub" {
  project = var.project_id
  role    = "roles/pubsub.publisher"
  member  = "serviceAccount:${google_service_account.main.email}"
}

resource "google_project_iam_member" "sa_pubsub_sub" {
  project = var.project_id
  role    = "roles/pubsub.subscriber"
  member  = "serviceAccount:${google_service_account.main.email}"
}

resource "google_project_iam_member" "sa_storage" {
  project = var.project_id
  role    = "roles/storage.objectUser"
  member  = "serviceAccount:${google_service_account.main.email}"
}

resource "google_project_iam_member" "sa_cloudsql" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.main.email}"
}

# VPC Service Controls (would require org-level permissions)
# Uncomment when ready for production
# resource "google_access_context_manager_service_perimeter" "sapphire_perimeter" {
#   parent = "accessPolicies/${var.access_policy_id}"
#   name   = "accessPolicies/${var.access_policy_id}/servicePerimeters/sapphire_perimeter"
#   title  = "Sapphire Trading Perimeter"
#   status {
#     resources = ["projects/${var.project_number}"]
#     restricted_services = [
#       "storage.googleapis.com",
#       "bigquery.googleapis.com"
#     ]
#   }
# }

# Output WAF policy for reference
output "waf_policy_id" {
  value       = google_compute_security_policy.sapphire_waf.id
  description = "Cloud Armor WAF Policy ID - attach to backend services"
}
