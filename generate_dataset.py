# =============================================================================
# ASSUMPTIONS & COVARIATION RATIONALE
# =============================================================================
# Generates flight_log.csv for 5 distinct cargo drone missions (>=200 rows
# total). Each variable derives from per-mission config parameters rather
# than independent random sampling, so related variables move together.
#
# MISSIONS:
#   1. Ideal, small payload        - calm baseline, nominal drain reference
#   2. Good conditions, medium-max payload - isolates payload effect alone
#   3. Emerging storm              - wind/visibility/humidity/temperature
#                                     trend together over the flight
#   4. Big Drainage                - heavy payload + sustained headwind,
#                                     combined cause of faster-than-nominal
#                                     battery drain
#   5. Emergency delivery          - short hop at elevated cruise speed,
#                                     isolates speed as a third, independent
#                                     driver of battery drain and noise
#
# WEATHER (wind, visibility, humidity, temperature):
#   Linearly interpolated between a mission-specific start/end value
#   (constant when equal, trending when different) + jitter proportional
#   to the value, emulating sensor noise. Clamped to physical/sensor limits.
#
# WIND GUST:
#   gust = wind_speed * (1 + random_factor), factor in [0.2, 0.6], capped
#   at sensor ceiling (30 m/s). Always >= wind_speed by construction.
#
# ALTITUDE: trapezoidal climb -> cruise -> descent; climb/descent share
#   scales with cruise altitude tier.
#
# SPEED: zero during vertical climb/descent; cruise speed = base speed
#   (mission-specific, elevated for the urgent-delivery mission) reduced by
#   payload, headwind and gust-excess penalties. Coefficients are
#   calibration parameters, not measured aerodynamic constants.
#
# BATTERY: cumulative drain per 30s sample = idle drain (avionics always
#   on) + speed + payload + wind terms. Emergent drain rate, not a fixed
#   linear ramp - this is what produces mission 4's faster-than-nominal
#   depletion and mission 5's speed-driven depletion.
#
# NOISE: base rotor noise + payload/speed/wind contributions, attenuated
#   by altitude (distance from the fixed 25m ground reference point).
#   Clamped to the 40-90 dBA sensor range.
#
# TIMESTAMPS:
#   Each mission gets a random start time between May and September 2026
#   (summer season), so the calendar date stays consistent with the fixed
#   temperature values used across missions (15-20C) - a January date
#   at those temperatures would be physically implausible for a coastal
#   region. Samples advance in fixed 30s steps from that start.
# =============================================================================

import random
from datetime import datetime, timedelta
import csv
#random.seed(42)

def interpolate_with_jitter(start_value, end_value, num_rows, jitter_pct):
    values = []
    step = (end_value - start_value) / (num_rows - 1)
    if num_rows == 1:
        return [round(start_value, 3)]
    for i in range(num_rows):
        current_value = round((start_value) + i * step, 3)
        noise = random.uniform(-jitter_pct, jitter_pct) * current_value
        current_value = round(current_value + noise, 3)
        values.append(current_value)
    return values

def compute_gust(wind_series, max_gust=30):
    gust_series = []
    for wind_speed in wind_series:
        gust_factor = random.uniform(0.2, 0.6)
        gust = wind_speed * (1 + gust_factor)
        gust = max(0, min(gust, max_gust))
        gust_series.append(round(gust, 3))
    return gust_series

def generate_altitude_profile(cruise_altitude, num_rows):
    if cruise_altitude <= 50:
        climb_pct = 0.15
        cruise_pct = 0.70
    elif cruise_altitude < 100:
        climb_pct = 0.20
        cruise_pct = 0.60
    else:
        climb_pct = 0.25
        cruise_pct = 0.50
    descent_pct = 1 - climb_pct - cruise_pct

    climb_rows = round(num_rows * climb_pct)
    cruise_rows = round(num_rows * cruise_pct)
    descent_rows = num_rows - climb_rows - cruise_rows

    climb_series = interpolate_with_jitter(0,cruise_altitude,climb_rows,0)
    cruise_series = [cruise_altitude] * cruise_rows
    descent_series = interpolate_with_jitter(cruise_altitude,0,descent_rows,0)
    altitude_series = climb_series + cruise_series + descent_series
    return altitude_series

def generate_speed_profile(cruise_altitude, num_rows, payload_kg, wind_series, gust_series, base_speed_ms=15):
    if cruise_altitude <= 50:
        climb_pct = 0.15
        cruise_pct = 0.70
    elif cruise_altitude < 100:
        climb_pct = 0.20
        cruise_pct = 0.60
    else:
        climb_pct = 0.25
        cruise_pct = 0.50

    descent_pct = 1 - climb_pct - cruise_pct

    climb_rows = round(num_rows * climb_pct)
    cruise_rows = round(num_rows * cruise_pct)
    descent_rows = num_rows - climb_rows - cruise_rows
    BASE_SPEED = base_speed_ms
    PAYLOAD_FACTOR = 0.4
    WIND_FACTOR = 0.12
    GUST_FACTOR = 0.08
    climb_series = interpolate_with_jitter(0, 0, climb_rows, 0)
    cruise_series = interpolate_with_jitter(BASE_SPEED, BASE_SPEED, cruise_rows, 0.03)
    descent_series = interpolate_with_jitter(0, 0, descent_rows, 0)
    payload_penalty = payload_kg * PAYLOAD_FACTOR

    for i in range(len(cruise_series)):
        wind_penalty = wind_series[i + climb_rows] * WIND_FACTOR
        gust_penalty = (gust_series[i + climb_rows] - wind_series[i + climb_rows]) * GUST_FACTOR
        cruise_series[i] -= payload_penalty
        cruise_series[i] -= wind_penalty
        cruise_series[i] -= gust_penalty
        cruise_series[i] = round(max(0, min(cruise_series[i], 20)), 3)
    
    speed_series = climb_series + cruise_series + descent_series
    return speed_series

def generate_battery_profile(num_rows, payload_kg, speed_series, wind_series):
    battery_series = []

    battery = 100
    IDLE_DRAIN = 0.5
    SPEED_FACTOR = 0.03
    PAYLOAD_FACTOR = 0.18
    WIND_FACTOR = 0.04

    for i in range(num_rows):
        drain = IDLE_DRAIN
        drain += speed_series[i] * SPEED_FACTOR
        drain += payload_kg * PAYLOAD_FACTOR
        drain += wind_series[i] * WIND_FACTOR
        battery -= drain
        battery = round(max(0, min(battery, 100)), 2)
        battery_series.append(battery)
    return battery_series

def generate_noise_profile(payload_kg, speed_series, wind_series, altitude_series):
    noise_series = []
    BASE_NOISE = 40
    SPEED_FACTOR = 1.5
    PAYLOAD_FACTOR = 4
    WIND_FACTOR = 0.05
    ALTITUDE_FACTOR = -0.1

    for i in range(len(speed_series)):
        noise = BASE_NOISE
        noise += payload_kg * PAYLOAD_FACTOR
        noise += speed_series[i] * SPEED_FACTOR
        noise += wind_series[i] * WIND_FACTOR
        noise += altitude_series[i] * ALTITUDE_FACTOR
        noise = max(40, min(noise, 90))
        noise_series.append(round(noise, 2))
    return noise_series

def generate_timestamp_series(num_rows):
    timestamp_series = []
    
    start_time = datetime(2026, random.randint(5, 9), random.randint(1, 28), random.randint(0, 23), random.randint(0, 59), 0)
    # start_time = datetime(2026, 7, 11, 10, 0, 0)

    for i in range(num_rows):
        timestamp = start_time + timedelta(seconds=30 * i)
        timestamp_series.append(timestamp.strftime("%Y-%m-%dT%H:%M:%SZ"))
    return timestamp_series

missions = [
    {
        "id": 1,
        "label": "Ideal, Small Payload",
        "duration_rows": 45,
        "payload_kg": round(random.uniform(1,1.5), 2),
        "wind_start_ms": 0.5,
        "wind_end_ms": 0.5,
        "cruise_altitude_m": 100,
        "visibility_start_m": 10000,
        "visibility_end_m": 10000,
        "humidity_start_pct": 60,
        "humidity_end_pct": 60,
        "temperature_start_c": 20,
        "temperature_end_c": 20,
    },
    {
        "id": 2,
        "label": "Good Conditions, Medium-Max Payload",
        "duration_rows": 55,
        "payload_kg": round(random.uniform(3.5, 4.5), 2),
        "wind_start_ms": 0.5,
        "wind_end_ms": 1,
        "cruise_altitude_m": 80,
        "visibility_start_m": 10000,
        "visibility_end_m": 10000,
        "humidity_start_pct": 60,
        "humidity_end_pct": 60,
        "temperature_start_c": 20,
        "temperature_end_c": 20,
    },
    {
        "id": 3,
        "label": "Emerging storm",
        "duration_rows": 50,
        "payload_kg": round(random.uniform(1,2), 2),
        "wind_start_ms": 5,
        "wind_end_ms": 18,
        "cruise_altitude_m": 75,
        "visibility_start_m": 5000,
        "visibility_end_m": 1000,
        "humidity_start_pct": 70,
        "humidity_end_pct": 93,
        "temperature_start_c": 20,
        "temperature_end_c": 15,
    },
    {
        "id": 4,
        "label": "Big Drainage",
        "duration_rows": 45,
        "payload_kg": round(random.uniform(4.5, 4.8), 2),
        "wind_start_ms": 18,
        "wind_end_ms": 18,
        "cruise_altitude_m": 70,
        "visibility_start_m": 9000,
        "visibility_end_m": 9000,
        "humidity_start_pct": 60,
        "humidity_end_pct": 60,
        "temperature_start_c": 17,
        "temperature_end_c": 17,
    },
    {
        "id": 5,
        "label": "Emergency Delivery",
        "duration_rows": 35,
        "payload_kg": round(random.uniform(0.5, 1), 2),
        "base_speed_ms": 18,
        "wind_start_ms": 5,
        "wind_end_ms": 5,
        "cruise_altitude_m": 35,
        "visibility_start_m": 7000,
        "visibility_end_m": 7000,
        "humidity_start_pct": 70,
        "humidity_end_pct": 70,
        "temperature_start_c": 20,
        "temperature_end_c": 20,
    },
]

dataset = []

for mission in missions:
    wind_series = interpolate_with_jitter(mission["wind_start_ms"],mission["wind_end_ms"],mission["duration_rows"],0.1)
    wind_series = [
        min(max(value, 0), 25)
        for value in wind_series
    ]
    visibility_series = interpolate_with_jitter(mission["visibility_start_m"],mission["visibility_end_m"],mission["duration_rows"],0.01)
    visibility_series = [
        min(max(value, 0), 10000)
    for value in visibility_series
    ]
    temperature_series = interpolate_with_jitter(mission["temperature_start_c"],mission["temperature_end_c"],mission["duration_rows"],0.05)
    temperature_series = [
        min(max(value, -5), 40)
        for value in temperature_series
    ]
    humidity_series = interpolate_with_jitter(mission["humidity_start_pct"],mission["humidity_end_pct"],mission["duration_rows"],0.05)
    humidity_series = [
        min(max(value, 0), 100)
        for value in humidity_series
    ]
    gust_series = compute_gust(wind_series)
    altitude_series = generate_altitude_profile(mission["cruise_altitude_m"],mission["duration_rows"])
    speed_series = generate_speed_profile(mission["cruise_altitude_m"],mission["duration_rows"],mission["payload_kg"],wind_series,gust_series,mission.get("base_speed_ms", 15))
    battery_series = generate_battery_profile(mission["duration_rows"],mission["payload_kg"],speed_series,wind_series)
    noise_series = generate_noise_profile(mission["payload_kg"],speed_series,wind_series,altitude_series)
    timestamp_series = generate_timestamp_series(mission["duration_rows"])
    
    mission["altitude_series"] = altitude_series
    mission["wind_series"] = wind_series
    mission["gust_series"] = gust_series
    mission["visibility_series"] = visibility_series
    mission["temperature_series"] = temperature_series
    mission["humidity_series"] = humidity_series
    mission["speed_series"] = speed_series
    mission["battery_series"] = battery_series
    mission["noise_series"] = noise_series
    mission["timestamp_series"] = timestamp_series

    for i in range(mission["duration_rows"]):
        row = {
            "timestamp": timestamp_series[i],
            "mission_id": mission["id"],
            "altitude_m": altitude_series[i],
            "speed_ms": speed_series[i],
            "wind_speed_ms": wind_series[i],
            "wind_gust_ms": gust_series[i],
            "temperature_c": temperature_series[i],
            "relative_humidity": humidity_series[i],
            "visibility_m": visibility_series[i],
            "battery_pct": battery_series[i],
            "payload_kg": mission["payload_kg"],
            "noise_dba": noise_series[i],
        }

        dataset.append(row)

with open("flight_log.csv", "w", newline="") as file:
    writer = csv.DictWriter(file, fieldnames=dataset[0].keys())
    writer.writeheader()
    writer.writerows(dataset)