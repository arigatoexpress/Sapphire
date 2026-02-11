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

variable "db_password" {
  description = "Cloud SQL password for trading_user. Set via tfvars or TF_VAR_db_password."
  type        = string
  sensitive   = true

  validation {
    condition     = length(var.db_password) >= 16
    error_message = "db_password must be at least 16 characters."
  }
}
