import pandas as pd

df = pd.read_csv('runs/2025-11-07_2227_1y/data/alerts/alerts_history.csv')
df['alert_date'] = pd.to_datetime(df['alert_date'])

# 70+ false positives
fps = df[(df['pump_score'] >= 70) & (df['outcome'] == 'false_positive')][
    ['ticker', 'alert_date', 'pump_score', 'daily_return', 'vol_z', 'return_5d', 'return_10d', 'days_to_bottom']
]

print("=== 70+ FALSE POSITIVES (The Problem) ===")
print(fps.to_string(index=False))
print(f"\nTotal: {len(fps)} alerts")

# 70+ confirmed pumps
pumps = df[(df['pump_score'] >= 70) & (df['outcome'].isin(['confirmed_pump', 'likely_pump']))][
    ['ticker', 'alert_date', 'pump_score', 'daily_return', 'vol_z', 'return_5d', 'return_10d']
]

print("\n=== 70+ CONFIRMED PUMPS (What's Working) ===")
print(pumps.to_string(index=False))
print(f"\nTotal: {len(pumps)} alerts")

# Compare features
if len(fps) > 0 and len(pumps) > 0:
    print("\n=== FEATURE COMPARISON ===")
    print(f"FP avg daily_return:  {fps['daily_return'].mean():.2%}")
    print(f"Pump avg daily_return: {pumps['daily_return'].mean():.2%}")
    print(f"FP avg vol_z:         {fps['vol_z'].mean():.2f}")
    print(f"Pump avg vol_z:       {pumps['vol_z'].mean():.2f}")