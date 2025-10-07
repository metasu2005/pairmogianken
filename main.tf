resource "aws_dynamodb_table" "this" {
  name         = var.table_name
  billing_mode = "PAY_PER_REQUEST"  # 検証はオンデマンドで簡単に

  hash_key  = "device_id"  # PK
  range_key = "ts"         # SK (ISO8601)

  attribute { name = "device_id" type = "S" }
  attribute { name = "ts"        type = "S" }
  attribute { name = "room_id"   type = "S" }

  global_secondary_index {
    name            = var.gsi1_name
    hash_key        = "room_id"   # GSI1PK
    range_key       = "ts"        # GSI1SK
    projection_type = "ALL"
  }

  ttl {
    attribute_name = "expires_at"  # Number(Epoch秒)が入っている行は自動削除対象
    enabled        = true
  }

  server_side_encryption {
    enabled = true
  }

  point_in_time_recovery {
    enabled = true
  }

  stream_enabled   = true
  stream_view_type = "NEW_AND_OLD_IMAGES"

  tags = {
    Project = "adv02"
    Env     = "dev"
  }
}

# ダミーデータ（少量ならTerraformで投入OK）
resource "aws_dynamodb_table_item" "seed_1" {
  table_name = aws_dynamodb_table.this.name
  hash_key   = "device_id"
  range_key  = "ts"

  item = jsonencode({
    device_id     = { S = "fridge_01" }
    ts            = { S = "2024-12-01T10:00:00Z" }
    room_id       = { S = "room_101" }
    temperature   = { N = "5.5" }
    device_status = { S = "ok" }
  })
}

resource "aws_dynamodb_table_item" "seed_2" {
  table_name = aws_dynamodb_table.this.name
  hash_key   = "device_id"
  range_key  = "ts"

  item = jsonencode({
    device_id     = { S = "fridge_01" }
    ts            = { S = "2024-12-01T10:05:00Z" }
    room_id       = { S = "room_101" }
    temperature   = { N = "5.7" }
    device_status = { S = "ok" }
  })
}

output "table_name" { value = aws_dynamodb_table.this.name }
output "gsi1_name"  { value = var.gsi1_name }
