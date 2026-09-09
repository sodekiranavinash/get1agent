# Legacy module rename (data_plane → vpc_rds)
moved {
  from = module.data_plane[0]
  to   = module.vpc_rds[0]
}

# vpc_rds → network + rds
moved {
  from = module.vpc_rds[0].aws_vpc.main
  to   = module.network[0].aws_vpc.main
}

moved {
  from = module.vpc_rds[0].aws_internet_gateway.main
  to   = module.network[0].aws_internet_gateway.main
}

moved {
  from = module.vpc_rds[0].aws_subnet.public
  to   = module.network[0].aws_subnet.public
}

moved {
  from = module.vpc_rds[0].aws_subnet.private_a
  to   = module.network[0].aws_subnet.private_a
}

moved {
  from = module.vpc_rds[0].aws_subnet.private_b
  to   = module.network[0].aws_subnet.private_b
}

moved {
  from = module.vpc_rds[0].aws_route_table.public
  to   = module.network[0].aws_route_table.public
}

moved {
  from = module.vpc_rds[0].aws_route_table_association.public
  to   = module.network[0].aws_route_table_association.public
}

moved {
  from = module.vpc_rds[0].aws_route_table.private
  to   = module.network[0].aws_route_table.private
}

moved {
  from = module.vpc_rds[0].aws_route_table_association.private_a
  to   = module.network[0].aws_route_table_association.private_a
}

moved {
  from = module.vpc_rds[0].aws_route_table_association.private_b
  to   = module.network[0].aws_route_table_association.private_b
}

moved {
  from = module.vpc_rds[0].aws_db_subnet_group.postgres
  to   = module.network[0].aws_db_subnet_group.postgres
}

moved {
  from = module.vpc_rds[0].aws_security_group.jumpbox
  to   = module.network[0].aws_security_group.jumpbox
}

moved {
  from = module.vpc_rds[0].aws_security_group.postgres
  to   = module.network[0].aws_security_group.postgres
}

moved {
  from = module.vpc_rds[0].aws_security_group_rule.postgres_from_jumpbox
  to   = module.network[0].aws_security_group_rule.postgres_from_jumpbox
}

moved {
  from = module.vpc_rds[0].aws_iam_role.jumpbox
  to   = module.network[0].aws_iam_role.jumpbox
}

moved {
  from = module.vpc_rds[0].aws_iam_role_policy_attachment.jumpbox_ssm
  to   = module.network[0].aws_iam_role_policy_attachment.jumpbox_ssm
}

moved {
  from = module.vpc_rds[0].aws_iam_instance_profile.jumpbox
  to   = module.network[0].aws_iam_instance_profile.jumpbox
}

moved {
  from = module.vpc_rds[0].aws_instance.jumpbox
  to   = module.network[0].aws_instance.jumpbox
}

moved {
  from = module.vpc_rds[0].aws_db_instance.postgres
  to   = module.rds[0].aws_db_instance.postgres
}

moved {
  from = module.vpc_rds[0].random_password.db_master
  to   = module.rds[0].random_password.db_master
}

moved {
  from = module.vpc_rds[0].aws_ssm_parameter.db_credentials
  to   = module.rds[0].aws_ssm_parameter.db_credentials
}

moved {
  from = module.vpc_rds[0].aws_ssm_parameter.db_connection
  to   = module.rds[0].aws_ssm_parameter.db_connection
}

# Optional components now use count
moved {
  from = module.api_gateway
  to   = module.api_gateway[0]
}

moved {
  from = module.challan_extractor
  to   = module.challan_extractor[0]
}
