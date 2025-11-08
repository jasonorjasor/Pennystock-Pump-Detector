import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
import os
from scipy.stats import chisquare
RUN_DIR = os.environ.get("RUN_DIR", "runs/LATEST")

# If 'runs/LATEST' doesn't exist, pick the newest run automatically
if RUN_DIR == "runs/LATEST":
    base = "runs"
    if not os.path.isdir(base) or len(os.listdir(base)) == 0:
        raise FileNotFoundError("No runs found. Run pump_detector.py first.")
    RUN_DIR = max(
        [os.path.join(base, d) for d in os.listdir(base) if os.path.isdir(os.path.join(base, d))],
        key=os.path.getmtime
    )

print(f"Using run folder: {RUN_DIR}")
os.makedirs(os.path.join(RUN_DIR, 'data/analysis'), exist_ok=True)




# Create output directory
os.makedirs('data/analysis', exist_ok=True)

print("="*80)
print("PUMP PATTERN ANALYSIS")
print("="*80)

# ============================================================================
# LOAD DATA
# ============================================================================



print("Loading data...")

signals_dir = os.path.join(RUN_DIR, "data", "signals_csv")
master_path = os.path.join(signals_dir, "MASTER_TRUTH_WITH_EPISODES.csv")
episodes_path = os.path.join(signals_dir, "PUMP_EPISODES.csv")

print(f" Signals directory: {signals_dir}")
print(f" Looking for master: {master_path}")
print(f" Looking for episodes: {episodes_path}")

# Check if files exist
if not os.path.exists(master_path):
    print(f"\n ERROR: Master file not found!")
    print(f"   Expected: {master_path}")
    print(f"   Directory contents:")
    if os.path.exists(signals_dir):
        print(f"   {os.listdir(signals_dir)}")
    else:
        print(f"   Directory doesn't exist: {signals_dir}")
    raise FileNotFoundError(f"Master file not found: {master_path}")

if not os.path.exists(episodes_path):
    raise FileNotFoundError(f"Episodes file not found: {episodes_path}")

master = pd.read_csv(master_path)
episodes = pd.read_csv(episodes_path)

# Convert date columns right after reading the CSVs
# This ensures all date columns are real datetime objects (not strings)
master['signal_date'] = pd.to_datetime(master['signal_date'], errors='coerce')
episodes['start_date'] = pd.to_datetime(episodes['start_date'], errors='coerce')
episodes['end_date']   = pd.to_datetime(episodes['end_date'],   errors='coerce')

# Optional: drop rows where conversion failed (bad or missing dates)
master = master.dropna(subset=['signal_date'])
episodes = episodes.dropna(subset=['start_date', 'end_date'])

print(f"Loaded {len(master)} signals and {len(episodes)} episodes (dates converted)")

# ============================================================================
# SECTION 1: EPISODE PROGRESSION ANALYSIS
# ============================================================================

print("\n" + "="*80)
print("SECTION 1: EPISODE PROGRESSION ANALYSIS")
print("="*80)
print("Question: Do pump scores rise BEFORE the price peaks?")

# Get multi-signal episodes only
multi_episodes = episodes[episodes['signal_count'] >= 2].copy()

if len(multi_episodes) > 0:
    print(f"\n Analyzing {len(multi_episodes)} multi-day campaigns...")
    
    progression_data = []
    
    for _, episode in multi_episodes.iterrows():
        episode_key = episode['episode_key']
        ticker = episode['ticker']
        
        # Get all signals in this episode
        episode_signals = master[master['episode_key'] == episode_key].sort_values('signal_date')
        
        if len(episode_signals) >= 2:
            # Calculate day number within episode
            start_date = episode_signals['signal_date'].min()
            
            for idx, signal in episode_signals.iterrows():
                
                signal_date = pd.to_datetime(signal['signal_date'])
                days_from_start = (signal['signal_date'] - start_date).days
                
                progression_data.append({
                    'episode_key': episode_key,
                    'ticker': ticker,
                    'day': days_from_start,
                    'pump_score': signal['pump_score'],
                    'signal_return': signal['signal_return'],
                    'vol_z': signal['vol_z']
                })
    
    progression_df = pd.DataFrame(progression_data)
    
    # Calculate average progression
    avg_progression = progression_df.groupby('day').agg({
        'pump_score': 'mean',
        'signal_return': 'mean',
        'vol_z': 'mean'
    }).reset_index()
    
    print("\n Average Progression Pattern:")
    print(avg_progression.to_string(index=False))
    
    
    if len(avg_progression) >= 2:
        day0_score = avg_progression[avg_progression['day'] == 0]['pump_score'].values[0]
        max_idx = avg_progression['pump_score'].idxmax()
        max_day_num = avg_progression.loc[max_idx, 'day']
        
        print(f"\n KEY FINDING:")
        print(f"  Day 0 avg score: {day0_score:.1f}")
        print(f"  Peak score on day: {max_day_num}")
        
        if max_day_num > 0:
            print(f"    EARLY WARNING: Scores peak {max_day_num} day(s) after first signal")
            print(f"  → Real-time monitoring could provide advance notice")
        else:
            print(f"     NO EARLY WARNING: Scores peak on first day")
            print(f"  → Real-time monitoring won't help (too late)")
    
    # Visualization
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
    
    # Top: Individual episodes (scatter) - show first 10 for clarity
    for episode_key in progression_df['episode_key'].unique()[:10]:
        episode_data = progression_df[progression_df['episode_key'] == episode_key]
        ax1.plot(episode_data['day'], episode_data['pump_score'], 
                marker='o', alpha=0.3, linewidth=1)
    
    ax1.set_ylabel('Pump Score', fontweight='bold')
    ax1.set_title('Episode Progression: Individual Campaigns (Top 10)', fontweight='bold')
    ax1.grid(alpha=0.3)
    
    # Bottom: Average progression (line)
    ax2.plot(avg_progression['day'], avg_progression['pump_score'], 
            marker='o', linewidth=3, markersize=8, color='red')
    ax2.fill_between(avg_progression['day'], 0, avg_progression['pump_score'], 
                     alpha=0.3, color='red')
    ax2.set_xlabel('Days from First Signal', fontweight='bold')
    ax2.set_ylabel('Avg Pump Score', fontweight='bold')
    ax2.set_title('Average Progression Pattern', fontweight='bold')
    ax2.grid(alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(os.path.join(RUN_DIR, 'data/analysis/episode_progression.png'), dpi=300, bbox_inches='tight')
    plt.close()

else:
    print("\n No multi-day campaigns found")

# ============================================================================
# SECTION 2: TICKER INTERVAL ANALYSIS
# ============================================================================

print("\n" + "="*80)
print("SECTION 2: TICKER INTERVAL ANALYSIS")
print("="*80)
print("Question: Do tickers pump on predictable intervals?")

# Calculate intervals for tickers with 3+ episodes
high_risk_tickers = episodes.groupby('ticker').size()
high_risk_tickers = high_risk_tickers[high_risk_tickers >= 3].index

interval_analysis = []

for ticker in high_risk_tickers:
    ticker_episodes = episodes[episodes['ticker'] == ticker].sort_values('start_date')
    
    if len(ticker_episodes) >= 2:
        
        end_to_start_intervals = []
        start_to_start_intervals = []
        
        for i in range(1, len(ticker_episodes)):
            prev_end = ticker_episodes.iloc[i-1]['end_date']
            prev_start = ticker_episodes.iloc[i-1]['start_date']
            curr_start = ticker_episodes.iloc[i]['start_date']
            
            end_to_start = (curr_start - prev_end).days
            start_to_start = (curr_start - prev_start).days
            
            end_to_start_intervals.append(end_to_start)
            start_to_start_intervals.append(start_to_start)
        
        if end_to_start_intervals:
            avg_gap = np.mean(end_to_start_intervals)
            avg_cycle = np.mean(start_to_start_intervals)
            std_gap = np.std(end_to_start_intervals)
            cv = std_gap / avg_gap if avg_gap > 0 else 0
            
            # Predict next pump using gap metric
            last_end = ticker_episodes.iloc[-1]['end_date']
            predicted_next = last_end + timedelta(days=int(avg_gap))
            
            interval_analysis.append({
                'ticker': ticker,
                'num_episodes': len(ticker_episodes),
                'avg_gap_days': avg_gap,
                'avg_cycle_days': avg_cycle,
                'std_gap_days': std_gap,
                'coefficient_variation': cv,
                'last_pump': last_end.strftime('%Y-%m-%d'),
                'predicted_next': predicted_next.strftime('%Y-%m-%d'),
                'predictability': 'HIGH' if cv < 0.3 else 'MEDIUM' if cv < 0.6 else 'LOW'
            })

interval_df = pd.DataFrame(interval_analysis)
interval_df = interval_df.sort_values('coefficient_variation')

print("\n Interval Predictability:")
print(interval_df.to_string(index=False))

# Save to CSV
interval_df.to_csv(os.path.join(RUN_DIR, 'data/analysis/ticker_intervals.csv'), index=False)


# Key findings
print("\n KEY FINDINGS:")
highly_predictable = interval_df[interval_df['predictability'] == 'HIGH']
if len(highly_predictable) > 0:
    print(f"\n {len(highly_predictable)} ticker(s) have PREDICTABLE pump cycles:")
    for _, row in highly_predictable.iterrows():
        print(f"  {row['ticker']:6s}: Pumps every ~{row['avg_cycle_days']:.0f} days "
              f"(~{row['avg_gap_days']:.0f} day gap, next: {row['predicted_next']})")
else:
    print("\n  No tickers show highly predictable patterns")

# Visualization
if len(interval_df) > 0:
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))
    
    # Left: Average intervals
    interval_df_sorted = interval_df.sort_values('avg_gap_days', ascending=False)
    ax1.barh(interval_df_sorted['ticker'], interval_df_sorted['avg_gap_days'])
    ax1.set_xlabel('Average Days Between Pumps', fontweight='bold')
    ax1.set_title('Pump Frequency by Ticker', fontweight='bold')
    ax1.grid(axis='x', alpha=0.3)
    
    # Right: Predictability scatter
    colors = {'HIGH': 'green', 'MEDIUM': 'orange', 'LOW': 'red'}
    for pred in ['HIGH', 'MEDIUM', 'LOW']:
        subset = interval_df[interval_df['predictability'] == pred]
        if len(subset) > 0:
            ax2.scatter(subset['avg_gap_days'], subset['coefficient_variation'], 
                       label=pred, s=100, alpha=0.6, color=colors[pred])
    
    ax2.set_xlabel('Average Gap (days)', fontweight='bold')
    ax2.set_ylabel('Coefficient of Variation', fontweight='bold')
    ax2.set_title('Pump Predictability', fontweight='bold')
    ax2.legend()
    ax2.grid(alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(os.path.join(RUN_DIR, 'data/analysis/ticker_intervals.png'), dpi=300, bbox_inches='tight')

    plt.close()

# ============================================================================
# SECTION 3: TEMPORAL PATTERNS
# ============================================================================

print("\n" + "="*80)
print("SECTION 3: TEMPORAL PATTERNS")
print("="*80)
print("Question: Do pumps cluster on certain days/months?")

# Add temporal features
master['day_of_week'] = master['signal_date'].dt.day_name()
master['month'] = master['signal_date'].dt.month_name()

master['year_week'] = master['signal_date'].dt.strftime('%Y-W%U')

# Only confirmed/likely pumps
pumps_only = master[master['classification'].isin(['confirmed_pump', 'likely_pump'])]

# Day of week analysis
dow_counts = pumps_only['day_of_week'].value_counts()
dow_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
dow_counts = dow_counts.reindex(dow_order, fill_value=0)

print("\n Pumps by Day of Week:")
for day, count in dow_counts.items():
    pct = count / dow_counts.sum() * 100
    bar = '█' * int(pct / 2)
    print(f"  {day:10s}: {count:3d} ({pct:5.1f}%) {bar}")

# Monthly analysis
month_counts = pumps_only['month'].value_counts()

print("\n Pumps by Month:")
for month, count in month_counts.items():
    pct = count / month_counts.sum() * 100
    bar = '█' * int(pct / 2)
    print(f"  {month:10s}: {count:3d} ({pct:5.1f}%) {bar}")

# Visualization: Heatmap (matplotlib only, no seaborn)
pivot_data = pumps_only.groupby(['year_week', 'day_of_week']).size().reset_index(name='count')
pivot_table = pivot_data.pivot(index='year_week', columns='day_of_week', values='count').fillna(0)
pivot_table = pivot_table.reindex(columns=dow_order, fill_value=0)

plt.figure(figsize=(12, 8))
plt.imshow(pivot_table.values, cmap='YlOrRd', aspect='auto')
plt.colorbar(label='Number of Pumps')
plt.xticks(range(len(dow_order)), dow_order, rotation=45, ha='right')
plt.yticks(range(len(pivot_table)), pivot_table.index, fontsize=8)
plt.xlabel('Day of Week', fontweight='bold')
plt.ylabel('Year-Week', fontweight='bold')
plt.title('Temporal Pump Clustering', fontweight='bold', fontsize=14)
plt.tight_layout()
plt.savefig(os.path.join(RUN_DIR, 'data/analysis/temporal_heatmap.png'), dpi=300, bbox_inches='tight')
plt.close()


total_pumps = dow_counts.sum()
expected_per_day = total_pumps / 5
chi2, p_value = chisquare(dow_counts.values, f_exp=[expected_per_day] * 5)

print(f"\n🎯 Statistical Test:")
print(f"  Chi-square test for uniform distribution: p = {p_value:.4f}")
if p_value < 0.05:
    print(f"    SIGNIFICANT: Pumps are NOT uniformly distributed")
    max_day = dow_counts.idxmax()
    print(f"  → {max_day} has significantly more pumps ({dow_counts[max_day]} vs expected {expected_per_day:.1f})")
else:
    print(f"    NOT SIGNIFICANT: Pumps appear randomly distributed")
    print(f"  → No clear day-of-week pattern")

# ============================================================================
# SECTION 4: SUMMARY STATISTICS
# ============================================================================

print("\n" + "="*80)
print("GENERATING SUMMARY STATISTICS")
print("="*80)

summary = f"""
PUMP DETECTION SYSTEM - ANALYSIS SUMMARY
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

{'='*60}
OVERALL STATISTICS
{'='*60}
Total signals detected: {len(master)}
Confirmed pumps: {len(master[master['classification'] == 'confirmed_pump'])}
Likely pumps: {len(master[master['classification'] == 'likely_pump'])}
Pump detection rate: {(len(pumps_only) / len(master) * 100):.1f}%

Total episodes: {len(episodes)}
Multi-day campaigns: {len(episodes[episodes['signal_count'] >= 2])}
Single-day pumps: {len(episodes[episodes['signal_count'] == 1])}

{'='*60}
TOP FINDINGS
{'='*60}
"""

# Add interval findings
if len(highly_predictable) > 0:
    summary += f"\n✅ {len(highly_predictable)} ticker(s) show PREDICTABLE pump cycles:\n"
    for _, row in highly_predictable.iterrows():
        summary += f"  - {row['ticker']}: Every ~{row['avg_cycle_days']:.0f} days (next: {row['predicted_next']})\n"
else:
    summary += "\n  No tickers show predictable timing patterns\n"

# Add temporal findings
if p_value < 0.05:
    max_day = dow_counts.idxmax()
    summary += f"\n Pumps cluster on {max_day}s ({dow_counts[max_day]} occurrences, p={p_value:.4f})\n"
else:
    summary += f"\n  Pumps are evenly distributed across weekdays (p={p_value:.4f})\n"

summary += f"\n{'='*60}\n"

# Save summary
with open(os.path.join(RUN_DIR, 'data/analysis/summary_stats.txt'), 'w', encoding='utf-8') as f:
    f.write(summary)

print(summary)


print("\n" + "="*80)
print("ANALYSIS COMPLETE")
print("="*80)
