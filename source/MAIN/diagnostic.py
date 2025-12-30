import pandas as pd

df = pd.read_csv('runs/2025-11-07_2227_1y/data/alerts/alerts_history.csv')
df['alert_date'] = pd.to_datetime(df['alert_date'])

# Filter to classified only
classified = df[df['outcome'].isin(['confirmed_pump', 'likely_pump', 'false_positive', 'uncertain'])]

print("=== OVERALL METRICS ===")
print(f"Total alerts: {len(df)}")
print(f"Classified: {len(classified)}")

if len(classified) > 0:
    pumps = len(classified[classified['outcome'].isin(['confirmed_pump', 'likely_pump'])])
    precision = pumps / len(classified) * 100
    print(f"Precision: {precision:.1f}% ({pumps}/{len(classified)})")

# Check 70+ bin
high_scores = classified[classified['pump_score'] >= 70]
if len(high_scores) > 0:
    pumps_high = len(high_scores[high_scores['outcome'].isin(['confirmed_pump', 'likely_pump'])])
    precision_high = pumps_high / len(high_scores) * 100
    print(f"\n70+ Bin: {precision_high:.1f}% ({pumps_high}/{len(high_scores)})")

# Check if the new rule caught any "delayed dumps"
delayed = df[
    (df['return_5d'] > 0.05) & 
    (df['return_10d'].notna()) &
    (df['return_10d'] < -0.05) &
    (df['outcome'] == 'likely_pump')
]

print(f"\nDelayed dumps caught: {len(delayed)}")
if len(delayed) > 0:
    print(delayed[['ticker', 'alert_date', 'return_5d', 'return_10d']])

# Show 70+ false positives
fps_70 = df[(df['pump_score'] >= 70) & (df['outcome'] == 'false_positive')]
print("=== 70+ FALSE POSITIVES ===")
print(fps_70[['ticker', 'alert_date', 'pump_score', 'daily_return', 'return_5d', 'return_10d']].to_string(index=False))

# Show 70+ pumps for comparison
pumps_70 = df[(df['pump_score'] >= 70) & (df['outcome'].isin(['confirmed_pump', 'likely_pump']))]
print("\n=== 70+ CONFIRMED PUMPS ===")
print(pumps_70[['ticker', 'alert_date', 'pump_score', 'daily_return', 'return_5d', 'return_10d']].to_string(index=False))