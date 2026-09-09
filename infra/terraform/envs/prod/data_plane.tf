module "data_plane" {
  count  = var.enable_data_plane ? 1 : 0
  source = "../../modules/data_plane"

  name_prefix = "get1agent-prod"
}
