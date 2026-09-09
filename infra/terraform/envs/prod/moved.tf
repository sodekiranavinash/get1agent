# Optional components now use count
moved {
  from = module.api_gateway
  to   = module.api_gateway[0]
}

moved {
  from = module.challan_extractor
  to   = module.challan_extractor[0]
}
