# S3 Vectors bucket holding the semantic index.
#
# One vector index per user is created lazily by the application (`idx-<sub>`),
# so Terraform only owns the bucket.

resource "aws_s3vectors_vector_bucket" "this" {
  vector_bucket_name = var.vector_bucket_name

  tags = var.tags
}
