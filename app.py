from fastapi import FastAPI, HTTPException, Query
from datetime import datetime, timedelta, timezone
import boto3
from boto3.dynamodb.conditions import Key

TABLE_NAME = "room_temperature"

app = FastAPI()
dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(TABLE_NAME)

ISO_FMT = "%Y-%m-%dT%H:%M:%SZ"


def parse_iso8601_or_none(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        # ここでは "2025-11-17T21:00:00Z" 前提
        return datetime.strptime(value, ISO_FMT).replace(tzinfo=timezone.utc)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid datetime format")


@app.get("/api/v1/temperature")
def get_temperature(
    room_id: str = Query(...),
    device_id: str = Query(...),
    start_time: str | None = Query(None),
    end_time: str | None = Query(None),
):
    # 時間範囲決定（未指定なら直近5分）
    end_dt = parse_iso8601_or_none(end_time)
    start_dt = parse_iso8601_or_none(start_time)

    if not end_dt or not start_dt:
        end_dt = datetime.now(timezone.utc)
        start_dt = end_dt - timedelta(minutes=5)

    if start_dt >= end_dt:
        raise HTTPException(status_code=422, detail="start_time must be before end_time")

    # DynamoDB クエリ
    start_key = f"{device_id}#{start_dt.strftime(ISO_FMT)}"
    end_key = f"{device_id}#{end_dt.strftime(ISO_FMT)}"

    resp = table.query(
        KeyConditionExpression=Key("room_id").eq(room_id)
        & Key("device_id_timestamp").between(start_key, end_key)
    )

    items = resp.get("Items", [])

    if not items:
        # 要件どおりエラーレスポンス
        raise HTTPException(status_code=404, detail="No temperature data available")

    temps = [float(i["temperature"]) for i in items if i.get("temperature") is not None]
    if not temps:
        raise HTTPException(status_code=422, detail="Temperature data invalid")

    avg_temp = sum(temps) / len(temps)

    return {
        "room_id": room_id,
        "device_id": device_id,
        "average_temperature": round(avg_temp, 2),
        "unit": "Celsius",
        "time_range": {
            "start": start_dt.strftime(ISO_FMT),
            "end": end_dt.strftime(ISO_FMT),
        },
    }
