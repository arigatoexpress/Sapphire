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
