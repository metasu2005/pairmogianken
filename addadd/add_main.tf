module "dynamodb" {
  source     = "../../modules/dynamodb"
  table_name = "adv02_dev_iot"
}

module "vpce_dynamodb" {
  source                   = "../../modules/vpce"
  vpc_id                   = module.vpc.vpc_id
  private_route_table_ids  = module.vpc.private_route_table_ids  # ルートテーブルIDをVPCモジュールから出す
}
