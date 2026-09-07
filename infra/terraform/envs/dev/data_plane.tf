module "data_plane" {
  count  = var.enable_data_plane ? 1 : 0
  source = "../../modules/data_plane"

  name_prefix             = "get1agent-dev"
  allowed_api_cidr_blocks = var.data_plane_api_cidr_blocks
  db_name                 = var.data_plane_db_name
  db_username             = var.data_plane_db_username
  db_iam_username         = var.data_plane_db_iam_username
}
