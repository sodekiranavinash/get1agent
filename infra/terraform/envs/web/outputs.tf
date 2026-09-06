output "site_bucket_name" {
  value = aws_s3_bucket.site.bucket
}

output "website_endpoint" {
  description = "Cloudflare origin: proxied CNAME for www -> this hostname (SSL mode Flexible)."
  value       = aws_s3_bucket_website_configuration.site.website_endpoint
}

output "website_domain" {
  value = aws_s3_bucket_website_configuration.site.website_domain
}

check "site_bucket_matches_hostname" {
  assert {
    condition     = aws_s3_bucket.site.bucket == "www.get1agent.com"
    error_message = "Website bucket must be named www.get1agent.com so the Host header from Cloudflare matches the S3 website bucket."
  }
}
