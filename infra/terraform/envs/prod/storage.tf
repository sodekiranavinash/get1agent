module "knowledge_storage" {
  count  = var.enable_backend_lambdas ? 1 : 0
  source = "../../modules/knowledge_storage"

  bucket_name = var.knowledge_bases_bucket_name

  enable_eventbridge = var.enable_ingestion

  allowed_origins = [
    "https://www.get1agent.com",
    "http://localhost:5173",
  ]
}
