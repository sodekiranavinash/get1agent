module "data_plane" {
  count  = var.enable_data_plane ? 1 : 0
  source = "../../modules/data_plane"

  name_prefix      = "get1agent-dev"
  api_hostname     = var.data_plane_api_hostname
  kong_ui_hostname = var.data_plane_kong_ui_hostname
}
