variable "project_id" {
  description = "The GCP project ID to deploy resources to."
  type        = string
  default     = "sapphire-479610"
}

variable "region" {
  description = "The GCP region to deploy resources to."
  type        = string
  default     = "us-east1"
}

variable "trading_db_password" {
  description = "Cloud SQL trading user password. Provide via tfvars or secret-backed CI variables."
  type        = string
  sensitive   = true
}
