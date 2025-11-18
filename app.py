from fastapi import FastAPI, HTTPException, Query
from datetime import datetime, timedelta, timezone
from typing import Optional
import os

import boto3
from boto3.dynamodb.conditions import Key

# =========================
# 設定
# =========================

TABLE_NAME = os.getenv("TABLE_NAME", "")
REGION = os.getenv("AWS_REGION", "ap-northeast-1")

ISO_FMT = "%Y-%m-%dT%H:%M:%SZ"

dynamodb = boto3.resource("dynamodb", region_name=REGION)
table = dynamodb.Table(TABLE_NAME)

app = FastAPI()


# =========================
# Utility
# =========================

def parse_iso8601_or_none(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.strptime(value, ISO_FMT).replace(tzinfo=timezone.utc)
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail="Invalid datetime format. Use YYYY-MM-DDTHH:MM:SSZ",
        )


def convert_temperature(value: Optional[str]) -> Optional[float]:
    """
    temperature が「文字列」「null文字列」「数字文字列」など
    どれで来ても安全に扱えるようにする。
    """
    if value is None:
        return None
    if value.lower() == "null":  # "null" 文字列
        return None
    try:
        return float(value)
    except ValueError:
        return None


# =========================
# API
# =========================

@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/v1/temperature")
def get_temperature(
    device_id: str = Query(...),
    start_time: Optional[str] = Query(None),
    end_time: Optional[str] = Query(None),
):
    # ---- 時間補完 ----
    end_dt = parse_iso8601_or_none(end_time)
    start_dt = parse_iso8601_or_none(start_time)

    if not end_dt or not start_dt:
        end_dt = datetime.now(timezone.utc)
        start_dt = end_dt - timedelta(minutes=5)

    if start_dt >= end_dt:
        raise HTTPException(
            status_code=422, detail="start_time must be before end_time"
        )

    # ---- DynamoDB 検索 ----
    start_key = start_dt.strftime(ISO_FMT)
    end_key = end_dt.strftime(ISO_FMT)

    try:
        resp = table.query(
            KeyConditionExpression=Key("device_id").eq(device_id)
            & Key("timestamp").between(start_key, end_key)
        )
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to query database")

    items = resp.get("Items", [])
    if not items:
        raise HTTPException(status_code=404, detail="No temperature data available")

    # ---- temperature = String に対応した安全な変換 ----
    temps = []
    for item in items:
        temp_str = item.get("temperature")
        temp_val = convert_temperature(temp_str)
        if temp_val is not None:  # 有効な温度のみ集める
            temps.append(temp_val)

    if not temps:
        raise HTTPException(status_code=422, detail="Temperature data invalid")

    avg_temp = sum(temps) / len(temps)

    return {
        "device_id": device_id,
        "average_temperature": round(avg_temp, 2),
        "unit": "Celsius",
        "sample_count": len(temps),
        "time_range": {
            "start": start_dt.strftime(ISO_FMT),
            "end": end_dt.strftime(ISO_FMT),
        },
    }
