# The state location is not stored here. Copy backend.hcl.example to backend.hcl, fill in the
# bootstrap outputs, then run: terraform init -backend-config=backend.hcl
# The state file is never stored in the repository.
terraform {
  backend "s3" {
    bucket       = ""
    key          = ""
    region       = ""
    encrypt      = true
    use_lockfile = true
  }
}
