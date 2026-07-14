import json
import csv

def classify_segment(row: dict, thresholds: dict) -> dict:
    triggered_rules = []
    if row["wind_gust_ms"] > thresholds["extreme_gust_ms"]:
        triggered_rules.append("EXTREME_GUST")
    if row["visibility_m"] < thresholds["very_low_visibility_m"]:
        triggered_rules.append("VERY_LOW_VISIBILITY")
    if row["wind_gust_ms"] > thresholds["high_gust_ms"]:
        triggered_rules.append("HIGH_GUST")
    if row["visibility_m"] < thresholds["low_visibility_m"]:
        triggered_rules.append("LOW_VISIBILITY")
    if row["battery_pct"] < thresholds["low_battery_pct"]:
        triggered_rules.append("LOW_BATTERY")
    if row["wind_speed_ms"] > thresholds["high_wind_speed_ms"]:
        triggered_rules.append("HIGH_WIND_SPEED")
    if row["temperature_c"] < thresholds["low_temperature_c"]:
        triggered_rules.append("LOW_TEMPERATURE")
    if row["temperature_c"] > thresholds["high_temperature_c"]:
        triggered_rules.append("HIGH_TEMPERATURE")
        
    degraded_names = ["HIGH_GUST", "LOW_VISIBILITY", "LOW_BATTERY", "HIGH_WIND_SPEED", "LOW_TEMPERATURE", "HIGH_TEMPERATURE"]
    degraded_count = sum(1 for rule in triggered_rules if rule in degraded_names)

    if "EXTREME_GUST" in triggered_rules or "VERY_LOW_VISIBILITY" in triggered_rules:
        classification = "unsafe"
    elif degraded_count >= 2:
        classification = "unsafe"
        triggered_rules.append("COMPOUND_RISK")
    elif degraded_count == 1:
        classification = "degraded"
    else:
        classification = "safe"

    return {
        "classification": classification,
        "triggered_rules": triggered_rules
    }

with open("thresholds_config.json") as f:
    thresholds = json.load(f)

with open("flight_log.csv") as f:
    reader = csv.DictReader(f)
    rows = list(reader)

float_fields = ["altitude_m", "speed_ms", "wind_speed_ms", "wind_gust_ms",
                 "temperature_c", "relative_humidity", "visibility_m",
                 "battery_pct", "payload_kg", "noise_dba"]

for row in rows:
    row["mission_id"] = int(row["mission_id"])
    for field in float_fields:
        row[field] = float(row[field])

for row in rows:
    result = classify_segment(row, thresholds)
    row["classification"] = result["classification"]
    row["triggered_rules"] = result["triggered_rules"]

summary = {}

for row in rows:
    mid = row["mission_id"]
    if mid not in summary:
        summary[mid] = {"safe": 0, "degraded": 0, "unsafe": 0, "rules": set()}
    if row["classification"] == "safe":
        summary[mid]["safe"] += 1
    elif row["classification"] == "degraded":
        summary[mid]["degraded"] += 1
    elif row["classification"] == "unsafe":
        summary[mid]["unsafe"] += 1
    summary[mid]["rules"].update(row["triggered_rules"])

final_summary = []
for mid, data in summary.items():
    total = data["safe"] + data["degraded"] + data["unsafe"]
    final_summary.append({
        "mission_id": mid,
        "safe_count": data["safe"],
        "degraded_count": data["degraded"],
        "unsafe_count": data["unsafe"],
        "safe_pct": round(data["safe"] / total * 100, 1),
        "degraded_pct": round(data["degraded"] / total * 100, 1),
        "unsafe_pct": round(data["unsafe"] / total * 100, 1),
        "triggered_rules": ", ".join(sorted(data["rules"])),
    })

with open("mission_summary.csv", "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=final_summary[0].keys())
    writer.writeheader()
    writer.writerows(final_summary)