check "data_plane_ssh_cidr" {
  assert {
    condition = (
      !var.enable_data_plane ||
      length(var.data_plane_ssh_cidr_blocks) > 0
    )
    error_message = "Set data_plane_ssh_cidr_blocks to your public IP/32 in terraform.tfvars when enable_data_plane is true (e.g. [\"203.0.113.10/32\"])."
  }
}

module "data_plane" {
  count  = var.enable_data_plane ? 1 : 0
  source = "../../modules/data_plane"

  name_prefix             = "get1agent-dev"
  allowed_ssh_cidr_blocks = var.data_plane_ssh_cidr_blocks
  allowed_api_cidr_blocks = var.data_plane_api_cidr_blocks
  db_name                 = var.data_plane_db_name
  db_username             = var.data_plane_db_username
  db_iam_username         = var.data_plane_db_iam_username
}
