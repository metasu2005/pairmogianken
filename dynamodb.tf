variable "vpc_id" {}
variable "private_route_table_ids" { type = list(string) }

resource "aws_vpc_endpoint" "dynamodb" {
  vpc_id            = var.vpc_id
  service_name      = "com.amazonaws.ap-northeast-1.dynamodb"
  vpc_endpoint_type = "Gateway"

  route_table_ids = var.private_route_table_ids

  tags = {
    Name = "adv02-dev-dynamodb-endpoint"
  }
}
