# main.py
import os
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta, timezone

import boto3
from boto3.dynamodb.conditions import Key

AWS_REGION = os.getenv("AWS_REGION", "ap-northeast-1")
TABLE_NAME = os.getenv("DDB_TABLE_NAME", "")

dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
table = dynamodb.Table(TABLE_NAME)

class TimeRange(BaseModel):
    start: str
    end: str

class TemperatureResponse(BaseModel):
    device_id: str
    average_temperature: float
    unit: str = "Celsius"
    sample_count: int
    time_range: TimeRange

class TemperatureRecord(BaseModel):
    device_id: str
    timestamp: str
    room_id: Optional[str] = None
    temperature: Optional[float] = None
    device_status: Optional[str] = None

app = FastAPI()

def parse_iso8601(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))

def to_iso8601(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

@app.get("/api/v1/temperature", response_model=TemperatureResponse)
def get_average_temperature(
    device_id: str = Query(...),
    start_time: Optional[str] = Query(None),
    end_time: Optional[str] = Query(None),
):
    now = datetime.now(timezone.utc)

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

    temps = [item.get("temperature") for item in items if item.get("temperature") is not None]

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
    item = resp.get("Item")

    if not item:
        raise HTTPException(
            status_code=404,
            detail={"error_code": "RECORD_NOT_FOUND", "message": "Record not found"},
        )

    if item.get("temperature") is None:
        raise HTTPException(
            status_code=404,
            detail={"error_code": "TEMPERATURE_VALUE_NULL", "message": "Temperature is null"},
        )

    return TemperatureRecord(**item)
