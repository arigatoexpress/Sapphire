# Terraform (Reference)

This folder contains Terraform configs for parts of the Sapphire GCP environment.

Current status:

- The live environment may include manual `gcloud` changes (IAM, ingress, secret bindings, revisions).
- Treat `terraform/` as a reference unless/until it is actively applied and kept in sync.
- `terraform/legacy/` contains older experiments and should not be assumed correct.

Source-of-truth for what is running:

- `docs/CLOUD_ENVIRONMENT.md`
- `gcloud run services describe ...`
