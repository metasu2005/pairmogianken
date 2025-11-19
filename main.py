import os
from fastapi import FastAPI, HTTPException, Query # FastAPI
from pydantic import BaseModel # レスポンスのスキーマ管理
from typing import Optional 
from datetime import datetime, timedelta, timezone

import boto3 # AWS SDK
from boto3.dynamodb.conditions import Key

# 環境変数とDynamoDBの初期化
AWS_REGION = os.getenv("AWS_REGION", "ap-northeast-1")
TABLE_NAME = os.getenv("DDB_TABLE_NAME", "")

dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
table = dynamodb.Table(TABLE_NAME)

# 返り値のJSONをPydanticで管理
class TimeRange(BaseModel):
    start: str
    end: str

class TemperatureResponse(BaseModel):
    device_id: str
    average_temperature: float
    unit: str = "Celsius"
    sample_count: int
    time_range: TimeRange

# DynamoDBのItemに完全一致した構造
class TemperatureRecord(BaseModel):
    device_id: str
    timestamp: str
    room_id: Optional[str] = None
    temperature: Optional[float] = None
    device_status: Optional[str] = None

# FastAPIアプリ本体
app = FastAPI()

# ALB用ヘルスチェックAPI
@app.get("/health")
def health():
    return {"status": "ok"}

# 時刻のパース関数
def parse_iso8601(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))

def to_iso8601(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

# 平均温度API
@app.get("/api/v1/temperature", response_model=TemperatureResponse)
def get_average_temperature(
    device_id: str = Query(...),
    start_time: Optional[str] = Query(None),
    end_time: Optional[str] = Query(None),
):
    now = datetime.now(timezone.utc)

# 時間指定または直近5分のデフォルト範囲を計算
    if start_time and end_time:
        start_dt = parse_iso8601(start_time)
        end_dt = parse_iso8601(end_time)
    else:
        end_dt = now
        start_dt = end_dt - timedelta(minutes=5)
        start_time = to_iso8601(start_dt)
        end_time = to_iso8601(end_dt)

    if start_dt >= end_dt:
        raise HTTPException(
            status_code=400,
            detail={"error_code": "INVALID_TIME_RANGE", "message": "start_time must be before end_time"},
        )

# DynamoDB Queryを実行
    resp = table.query(
        KeyConditionExpression=Key("device_id").eq(device_id)
        & Key("timestamp").between(start_time, end_time)
    )
    items = resp.get("Items", [])

    if not items:
        raise HTTPException(
            status_code=404,
            detail={"error_code": "NO_RECORDS_IN_RANGE", "message": "No temperature records in range"},
        )

    if all(not item.get("room_id") for item in items):
        raise HTTPException(
            status_code=404,
            detail={"error_code": "ROOM_NOT_FOUND", "message": "Room not found for this device"},
        )

    # ここを修正
    temps = []
    for item in items:

        # 温度値の正規化
        raw_temp = item.get("temperature")

        # DynamoDB 上で null / 未設定 のものはスキップ
        if raw_temp is None:
            continue

        # "null" という文字列や空文字もスキップしたい場合
        if isinstance(raw_temp, str):
            if raw_temp.strip().lower() in ("", "null", "none"):
                continue

        # 数値に変換できるものだけ採用
        try:
            temp_val = float(raw_temp)
        except (TypeError, ValueError):
            # 変な値が来てたら無視（もしくはここでエラー返す運用でもOK）
            continue

        temps.append(temp_val)

# エラー制御
    if not temps:
        raise HTTPException(
            status_code=404,
            detail={"error_code": "TEMPERATURE_VALUE_NULL", "message": "All temperature values are null"},
        )

    avg_temp = sum(temps) / len(temps)

    return TemperatureResponse(
        device_id=device_id,
        average_temperature=round(avg_temp, 2),
        unit="Celsius",
        sample_count=len(temps),
        time_range=TimeRange(start=start_time, end=end_time),
    )

# 単一レコードAPI
@app.get("/api/v1/temperature/record", response_model=TemperatureRecord)
def get_temperature_record(
    device_id: str = Query(...),
    timestamp: str = Query(...),
):
    resp = table.get_item(
        Key={
            "device_id": device_id,
            "timestamp": timestamp,
        }
    )

    # DynamoDBからget_item
    item = resp.get("Item")

    # レコード自体がない
    if not item:
        raise HTTPException(
            status_code=404,
            detail={"error_code": "RECORD_NOT_FOUND", "message": "Record not found"},
        )

    raw_temp = item.get("temperature")

    # 値が存在しない（null / "null" / "" / "none" 等）はここで 404
    if raw_temp is None or (isinstance(raw_temp, str) and raw_temp.strip().lower() in ("", "null", "none")):
        raise HTTPException(
            status_code=404,
            detail={"error_code": "TEMPERATURE_VALUE_MISSING", "message": "Temperature value does not exist"},
        )

    # 数値に変換できない値は 400（クライアント or データ不正）
    try:
        temp_val = float(raw_temp)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=400,
            detail={"error_code": "TEMPERATURE_VALUE_INVALID", "message": "Temperature value is invalid"},
        )

    # Pydantic の temperature: float に合わせて正規化
    item["temperature"] = temp_val

    return TemperatureRecord(**item)
