import json
import csv
import matplotlib.pyplot as plt
import numpy as np

with open("mission_summary.csv") as f:
    mission_summary = list(csv.DictReader(f))

with open("flight_log.csv") as f:
    flight_log = list(csv.DictReader(f))

mission_data = {}
for row in flight_log:
    row["mission_id"] = int(row["mission_id"])
    if row["mission_id"] not in mission_data:
        mission_data[row["mission_id"]] = []
    mission_data[row["mission_id"]].append(row)
    row["timestamp"] = row["timestamp"]
    row["altitude_m"] = float(row["altitude_m"])
    row["speed_ms"] = float(row["speed_ms"])
    row["wind_speed_ms"] = float(row["wind_speed_ms"])
    row["wind_gust_ms"] = float(row["wind_gust_ms"])
    row["temperature_c"] = float(row["temperature_c"])
    row["relative_humidity"] = float(row["relative_humidity"])
    row["visibility_m"] = float(row["visibility_m"])
    row["battery_pct"] = float(row["battery_pct"])
    row["payload_kg"] = float(row["payload_kg"])
    row["noise_dba"] = float(row["noise_dba"])

for row in mission_summary:
    row["mission_id"] = int(row["mission_id"])
    row["safe_count"] = int(row["safe_count"])
    row["degraded_count"] = int(row["degraded_count"])
    row["unsafe_count"] = int(row["unsafe_count"])
    row["safe_pct"] = float(row["safe_pct"])
    row["degraded_pct"] = float(row["degraded_pct"])
    row["unsafe_pct"] = float(row["unsafe_pct"])

def calculate_EEI(segment):
    wind_score = max(0, min(1, 1 - segment["wind_speed_ms"] / 25))
    gust_score = max(0, min(1, 1 - segment["wind_gust_ms"] / 30))
    temperature_score = max(0, min(1, 1 - abs(segment["temperature_c"] - 20) / 20))
    humidity_score = max(0, min(1, 1 - segment["relative_humidity"] / 100))
    visibility_score = max(0, min(1, segment["visibility_m"] / 10000))
    EEI = (wind_score + gust_score + temperature_score + humidity_score + visibility_score) / 5
    return EEI

EEI_scores = {}

for mission_id in mission_data:
    eei_scores = []
    for row in mission_data[mission_id]:
        eei_scores.append(calculate_EEI(row))
    EEI_scores[mission_id] = sum(eei_scores) / len(eei_scores)

def calculate_OEI(rows, summary):
    mission_duration_seconds = (len(rows) - 1) * 30
    battery_used = rows[0]["battery_pct"] - rows[-1]["battery_pct"]
    battery_consumption_rate = battery_used / mission_duration_seconds
    payload_to_battery_ratio = rows[0]["payload_kg"] / battery_used
    risk_exposure_time = (summary["degraded_pct"] + summary["unsafe_pct"]) / 100
    return {
        "battery_consumption_rate": battery_consumption_rate,
        "payload_to_battery_ratio": payload_to_battery_ratio,
        "risk_exposure_time": risk_exposure_time
    }

oei_data = {}

for summary in mission_summary:
    mission_id = summary["mission_id"]
    rows = mission_data[mission_id]
    oei_data[mission_id] = calculate_OEI(rows, summary)
   
max_rate = max(data["battery_consumption_rate"]for data in oei_data.values())
max_payload_ratio = max(data["payload_to_battery_ratio"]for data in oei_data.values())

OEI_scores = {}

for mission_id, data in oei_data.items():
    battery_score = 1 - data["battery_consumption_rate"] / max_rate
    payload_score = data["payload_to_battery_ratio"] / max_payload_ratio
    risk_score = 1 - data["risk_exposure_time"]
    OEI_scores[mission_id] = (battery_score + payload_score + risk_score) / 3

def calculate_NII(rows):
    noise_levels = [row["noise_dba"] for row in rows]
    average_noise = sum(noise_levels) / len(noise_levels)
    peak_noise = max(noise_levels)
    average_score = 1 - (average_noise - 40) / 50
    peak_score = 1 - (peak_noise - 40) / 50
    average_score = max(0, min(1, average_score))
    peak_score = max(0, min(1, peak_score))
    NII=(average_score + peak_score) / 2
    return NII
    
NII_scores = {}

for mission_id in mission_data:
    NII_scores[mission_id] = calculate_NII(mission_data[mission_id])

equal_weights = {
    "EEI": 0.333,
    "OEI": 0.333,
    "NII": 0.334
}

environment_weights = {
    "EEI": 0.60,
    "OEI": 0.20,
    "NII": 0.20
}

noise_weights = {
    "EEI": 0.20,
    "OEI": 0.20,
    "NII": 0.60
}

MPS_equal = {}
MPS_environment = {}
MPS_noise = {}

def calculate_MPS(EEI, OEI, NII, weights):
    MPS = weights["EEI"] * EEI + weights["OEI"] * OEI + weights["NII"] * NII
    return MPS

for mission_id in mission_data:
    EEI = EEI_scores[mission_id]
    OEI = OEI_scores[mission_id]
    NII = NII_scores[mission_id]

    MPS_equal[mission_id] = calculate_MPS(EEI, OEI, NII, equal_weights)
    MPS_environment[mission_id] = calculate_MPS(EEI, OEI, NII, environment_weights)
    MPS_noise[mission_id] = calculate_MPS(EEI, OEI, NII, noise_weights)

ranking_equal = sorted(MPS_equal.items(),key=lambda item: item[1],reverse=True)
ranking_environment = sorted(MPS_environment.items(),key=lambda item: item[1],reverse=True)
ranking_noise = sorted(MPS_noise.items(),key=lambda item: item[1],reverse=True)

equal_rank = {}
environment_rank = {}
noise_rank = {}

for position, (mission_id, score) in enumerate(ranking_equal, start=1):
    equal_rank[mission_id] = position

for position, (mission_id, score) in enumerate(ranking_environment, start=1):
    environment_rank[mission_id] = position

for position, (mission_id, score) in enumerate(ranking_noise, start=1):
    noise_rank[mission_id] = position

rank_changes = {}

for mission_id in mission_data:
    ranks = [
        equal_rank[mission_id],
        environment_rank[mission_id],
        noise_rank[mission_id]
    ]
    rank_changes[mission_id] = max(ranks) - min(ranks)

max_change = max(rank_changes.values())

most_sensitive = []

for mission_id, change in rank_changes.items():
    if change == max_change:
        most_sensitive.append(mission_id)

print("\n" + "=" * 95)
print("MISSION PERFORMANCE SUMMARY")
print("=" * 95)
print(
    f"{'Mission':<8}"
    f"{'Balanced MPS':>12}"
    f"{'Environment MPS':>15}"
    f"{'Noise MPS':>12}"
    f"{'Rank Change':>12}"
)
print("-" * 95)

for mission_id in sorted(mission_data):
    print(
        f"{mission_id:<8}"
        f"{MPS_equal[mission_id]:>12.3f}"
        f"{MPS_environment[mission_id]:>15.3f}"
        f"{MPS_noise[mission_id]:>12.3f}"
        f"{rank_changes[mission_id]:>12}"
    )

print("-" * 95)
print(
    f"Most sensitive mission(s): "
    f"{', '.join(f'Mission {m}' for m in most_sensitive)} "
    f"(rank change = {max_change})"
)
print("=" * 95)

missions_score = []

for mission_id, mps in ranking_equal:
    missions_score.append({
        "mission_id": mission_id,
        "equal_rank": equal_rank[mission_id],
        "environment_rank": environment_rank[mission_id],
        "noise_rank": noise_rank[mission_id],
        "EEI": EEI_scores[mission_id],
        "OEI": OEI_scores[mission_id],
        "NII": NII_scores[mission_id],
        "MPS": mps
    })

with open("missions_score.csv", "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=missions_score[0].keys())
    writer.writeheader()
    writer.writerows(missions_score)

fig, axes = plt.subplots(1, 3, figsize=(18, 6), sharey=True)

charts = [
    ("Balanced\n(EEI: 0.33 / OEI: 0.33 / NII : 0.34)", MPS_equal),
    ("Environment Priority\n(EEI: 0.60 / OEI: 0.20 / NII : 0.20)", MPS_environment),
    ("Noise Priority\n(EEI: 0.20 / OEI: 0.20 / NII : 0.60)", MPS_noise)
    ]

for ax, (title, scores) in zip(axes, charts):
    ranking = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    missions = [f"Mission {mission}" for mission, score in ranking]
    values = [score for mission, score in ranking]
    colors = plt.cm.RdYlGn(np.linspace(1, 0, len(values)))
    bars = ax.bar(missions, values, width = 0.8, color=colors, edgecolor="black", linewidth = 1)
    ax.set_title(title, fontsize=12, fontweight="bold")
    ax.set_ylim(0, 1)
    ax.set_xlabel("Mission", fontsize=11, fontweight="bold")
    ax.grid(axis="y", linestyle="--", alpha=0.25)
    for bar, value in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width()/2, value + 0.02, f"{value:.3f}", ha="center", va="bottom", fontsize=10, fontweight="bold")

axes[0].set_ylabel("MPS (Mission Performance Score)", fontsize=11, fontweight="bold")

note = (f"Most sensitive mission(s) to weighting choice: "f"{', '.join(f'Mission {m}' for m in most_sensitive)} "f"(rank change = {max_change})")

fig.suptitle("Mission Performance Ranking under Different Weight Configurations\n" + note, fontsize=16, fontweight="bold")
plt.tight_layout(rect=[0, 0, 1, 0.88])
plt.savefig("mission_performance_comparison.png", dpi=300)
plt.show()

missions_sorted = sorted(mission_data.keys())
x_labels = [f"Mission {m}" for m in missions_sorted]

eei_contrib = [EEI_scores[m] * equal_weights["EEI"] for m in missions_sorted]
oei_contrib = [OEI_scores[m] * equal_weights["OEI"] for m in missions_sorted]
nii_contrib = [NII_scores[m] * equal_weights["NII"] for m in missions_sorted]

fig2, ax2 = plt.subplots(figsize=(10, 6))

bars1 = ax2.bar(x_labels, eei_contrib, label="EEI (Environmental Efficiency Index)", color="#00A676", edgecolor="black", linewidth=1)
bars2 = ax2.bar( x_labels, oei_contrib, bottom=eei_contrib, label="OEI (Operational Efficiency Index)", color="#F77F00", edgecolor="black", linewidth=1)
bottom2 = [e + o for e, o in zip(eei_contrib, oei_contrib)]
bars3 = ax2.bar( x_labels, nii_contrib, bottom=bottom2, label="NII (Noise Impact Index)", color="#4361EE", edgecolor="black", linewidth=1)

for i in range(len(x_labels)):
    ax2.text(i, eei_contrib[i] / 2, f"{eei_contrib[i]:.3f}", ha="center", va="center", color="white", fontsize=9, fontweight="bold")
    ax2.text(i, eei_contrib[i] + oei_contrib[i] / 2, f"{oei_contrib[i]:.3f}", ha="center", va="center", color="white", fontsize=9, fontweight="bold")
    ax2.text(i, bottom2[i] + nii_contrib[i] / 2, f"{nii_contrib[i]:.3f}", ha="center", va="center", color="white", fontsize=9, fontweight="bold")
    total = eei_contrib[i] + oei_contrib[i] + nii_contrib[i]
    ax2.text(i, total + 0.02, f"{total:.3f}", ha="center", fontweight="bold", fontsize=10)

ax2.set_title("Mission Performance Score Composition (Balanced Weights)", fontsize=14, fontweight="bold")
ax2.set_xlabel("Mission", fontsize=11, fontweight="bold")
ax2.set_ylabel("Weighted Contribution to MPS", fontsize=11, fontweight="bold")
ax2.set_ylim(0, 1)
ax2.legend(loc="upper right", fontsize=10)
ax2.grid(axis="y", linestyle="--", alpha=0.25)
plt.tight_layout()
plt.savefig("mission_scores.png", dpi=300)
plt.show()