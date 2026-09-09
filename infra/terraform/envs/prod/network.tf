module "network" {
  count  = var.enable_network ? 1 : 0
  source = "../../modules/network"

  name_prefix = "get1agent-prod"
}
