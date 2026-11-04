variable "env" {
  description = "Environment name. Must be dev or live. Used in every resource name."
  type        = string

  validation {
    condition     = contains(["dev", "live"], var.env)
    error_message = "The env variable must be either \"dev\" or \"live\"."
  }
}

variable "bucket_regional_domain_name" {
  description = "Regional domain name of the site bucket, from the bucket_regional_domain_names output of the storage module."
  type        = string
}

variable "site_domain" {
  description = "Own domain for the site, for example signal.johnwasikye.com. Null keeps the cloudfront.net address. Setting it requests the certificate; attach_domain then serves the site under it."
  type        = string
  default     = null
}

variable "attach_domain" {
  description = "True once the certificate's validation record is in DNS and the certificate is issued. Only then does CloudFront serve site_domain."
  type        = bool
  default     = false

  validation {
    condition     = !var.attach_domain || var.site_domain != null
    error_message = "attach_domain can be true only when site_domain is set."
  }
}
