import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os
import glob

# ============================================================================ 
# CONFIGURATION
# ============================================================================ 


def find_latest_run():
    # find all subdirs under runs/, ignore a static 'LATEST' folder if present
    candidates = [
        d for d in glob.glob("runs/*/")
        if os.path.isdir(d) and os.path.basename(os.path.normpath(d)) != "LATEST"
    ]
    if not candidates:
        raise FileNotFoundError(
            "No timestamped run directories found in runs/. "
            "Run pump_detector.py and pump_analyzer.py first."
        )
    return max(candidates, key=os.path.getmtime)

RUN_DIR = find_latest_run()
print(f"Using data from: {RUN_DIR}")

INTERVALS_PATH = os.path.join(RUN_DIR, "data", "analysis", "ticker_intervals.csv")
MASTER_PATH    = os.path.join(RUN_DIR, "data", "signals_csv", "MASTER_TRUTH_WITH_EPISODES.csv")

TIER1_MIN_EPISODES = 8  # Daily monitoring
TIER2_MIN_EPISODES = 6  # Weekly monitoring
PUMP_THRESHOLD = 50

print("="*80)
print("TIERED PUMP MONITORING SYSTEM")
print("="*80)

# ============================================================================ 
# LOAD HISTORICAL DATA
# ============================================================================ 

if not os.path.exists(INTERVALS_PATH):
    raise FileNotFoundError(f"Intervals file not found: {INTERVALS_PATH}")
if not os.path.exists(MASTER_PATH):
    raise FileNotFoundError(f"Master truth file not found: {MASTER_PATH}")

intervals_df = pd.read_csv(INTERVALS_PATH)
master_df = pd.read_csv(MASTER_PATH)
master_df['signal_date'] = pd.to_datetime(master_df['signal_date'])

# ============================================================================ 
# TIER ASSIGNMENT
# ============================================================================ 

def assign_tiers(intervals_df):
    tiers = {'tier1': [], 'tier2': [], 'tier3': []}
    for _, row in intervals_df.iterrows():
        ticker = row['ticker']
        num_episodes = row['num_episodes']
        cv = row['coefficient_variation']

        if num_episodes >= TIER1_MIN_EPISODES or (num_episodes >= 7 and cv < 0.4):
            tiers['tier1'].append(ticker)
        elif num_episodes >= TIER2_MIN_EPISODES:
            tiers['tier2'].append(ticker)
        else:
            tiers['tier3'].append(ticker)
    return tiers

tiers = assign_tiers(intervals_df)

print("\nTier Assignment:")
print(f"  Tier 1 (Daily):   {len(tiers['tier1'])} tickers")
print(f"  Tier 2 (Weekly):  {len(tiers['tier2'])} tickers")
print(f"  Tier 3 (Ignore):  {len(tiers['tier3'])} tickers")

print("\nTier 1 (Daily Monitoring):")
for ticker in sorted(tiers['tier1']):
    row = intervals_df[intervals_df['ticker'] == ticker].iloc[0]
    print(f"  {ticker:6s}: {row['num_episodes']:2.0f} episodes, "
          f"{row['avg_gap_days']:5.1f}d avg, CV={row['coefficient_variation']:.2f}")

# ============================================================================ 
# LAST PUMP TRACKING
# ============================================================================ 

def get_last_pump_date(ticker, master_df):
    ticker_pumps = master_df[
        (master_df['ticker'] == ticker) &
        (master_df['classification'].isin(['confirmed_pump', 'likely_pump']))
    ]
    return ticker_pumps['signal_date'].max() if len(ticker_pumps) > 0 else None

last_pump_dates = {t: get_last_pump_date(t, master_df) for t in intervals_df['ticker']}

# ============================================================================ 
# SCORING
# ============================================================================ 

def calculate_pump_score(ticker_data):
    df = ticker_data.copy()
    df['vol_z'] = (df['Volume'] - df['Volume'].rolling(20).mean()) / \
                  (df['Volume'].rolling(20).std() + 1e-9)
    df['vol_ratio'] = df['Volume'] / (df['Volume'].rolling(20).mean() + 1e-9)
    df['vol_trend'] = df['Volume'].rolling(5).mean() / \
                      (df['Volume'].rolling(20).mean() + 1e-9)
    df['return'] = df['Close'].pct_change()
    df['price_z'] = (df['return'] - df['return'].rolling(20).mean()) / \
                    (df['return'].rolling(20).std() + 1e-9)
    df['gap_up'] = (df['Open'] - df['Close'].shift(1)) / (df['Close'].shift(1) + 1e-9)
    df['volatility'] = (df['High'] - df['Low']) / (df['Close'] + 1e-9)

    df['pump_score'] = 0
    df.loc[df['vol_z'] > 2, 'pump_score'] += 20
    df.loc[df['vol_z'] > 3, 'pump_score'] += 10
    df.loc[df['vol_ratio'] > 3, 'pump_score'] += 15
    df.loc[df['return'] > 0.1, 'pump_score'] += 20
    df.loc[df['return'] > 0.2, 'pump_score'] += 10
    df.loc[df['price_z'] > 2, 'pump_score'] += 15
    df.loc[df['gap_up'] > 0.05, 'pump_score'] += 10
    df.loc[df['volatility'] > 0.1, 'pump_score'] += 10

    synergy = (df['vol_trend'] > 1.2) & (df['return'] > 0.1)
    df.loc[synergy, 'pump_score'] += 10
    return df

# ============================================================================ 
# MONITORING
# ============================================================================ 

def check_ticker(ticker, tier, last_pump_date, avg_gap):
    try:
        df = yf.download(ticker, period="60d", interval="1d", progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.droplevel(1)
        if df.empty or len(df) < 25:
            return None

        df = calculate_pump_score(df)
        latest = df.iloc[-1]
        latest_date = df.index[-1]

        days_since_last = None
        status = "NEW"
        if last_pump_date is not None:
            days_since_last = (latest_date - last_pump_date).days
            if days_since_last > avg_gap * 1.2:
                status = "OVERDUE"
            elif days_since_last > avg_gap * 0.8:
                status = "DUE"
            elif days_since_last < avg_gap * 0.5:
                status = "TOO_SOON"
            else:
                status = "NORMAL"

        if latest['pump_score'] > PUMP_THRESHOLD:
            return {
                'ticker': ticker,
                'tier': tier,
                'date': latest_date.strftime('%Y-%m-%d'),
                'pump_score': latest['pump_score'],
                'close': latest['Close'],
                'volume': latest['Volume'],
                'vol_z': latest['vol_z'],
                'return': latest['return'],
                'days_since_last': days_since_last,
                'status': status
            }
        return None
    except Exception as e:
        print(f"  Error checking {ticker}: {e}")
        return None

# ============================================================================ 
# SCAN EXECUTION
# ============================================================================ 

def run_scan(tiers_to_check):
    print("\n" + "="*80)
    print(f"RUNNING SCAN: {', '.join(tiers_to_check).upper()}")
    print(f"Time: {datetime.now():%Y-%m-%d %H:%M:%S}")
    print("="*80)

    alerts = []
    for tier_name in tiers_to_check:
        tickers_to_check = tiers[tier_name]
        if len(tickers_to_check) == 0:
            continue
        print(f"\nChecking {tier_name.upper()} ({len(tickers_to_check)} tickers)...")
        for ticker in tickers_to_check:
            ticker_row = intervals_df[intervals_df['ticker'] == ticker]
            avg_gap = ticker_row['avg_gap_days'].values[0] if len(ticker_row) > 0 else 30
            last_pump = last_pump_dates.get(ticker)

            print(f"  Checking {ticker:6s}...", end=" ")
            alert = check_ticker(ticker, tier_name, last_pump, avg_gap)
            if alert:
                alerts.append(alert)
                print(f"PUMP DETECTED (score={alert['pump_score']:.0f}, {alert['status']})")
            else:
                print("OK")
    return alerts

# ============================================================================ 
# ALERT REPORTING
# ============================================================================ 

def generate_alert_report(alerts):
    if len(alerts) == 0:
        print("\n" + "="*80)
        print("NO PUMPS DETECTED")
        print("="*80)
        return

    print("\n" + "="*80)
    print(f"PUMP ALERTS ({len(alerts)} detected)")
    print("="*80)

    alerts = sorted(alerts, key=lambda x: x['pump_score'], reverse=True)
    for alert in alerts:
        print(f"\n{alert['ticker']:6s} - Score: {alert['pump_score']:.0f} ({alert['status']})")
        print(f"   Date: {alert['date']}")
        print(f"   Price: ${alert['close']:.2f}")
        print(f"   Volume: {alert['volume']:,.0f}")
        print(f"   Vol Z-Score: {alert['vol_z']:.2f}")
        print(f"   Return: {alert['return']*100:+.2f}%")
        if alert['days_since_last'] is not None:
            print(f"   Days since last pump: {alert['days_since_last']}")

    alerts_df = pd.DataFrame(alerts)
    alerts_dir = os.path.join(RUN_DIR, "data", "alerts")
    os.makedirs(alerts_dir, exist_ok=True)

    out_file = os.path.join(alerts_dir, f"pump_alerts_{datetime.now():%Y%m%d}.csv")
    alerts_df.to_csv(out_file, index=False)
    print(f"\nAlerts saved to: {out_file}")

# ============================================================================ 
# MAIN EXECUTION
# ============================================================================ 

if __name__ == "__main__":
    today = datetime.now()
    day_of_week = today.strftime('%A')
    print(f"\nToday is {day_of_week}")

    if day_of_week in ['Monday', 'Wednesday', 'Friday']:
        tiers_to_check = ['tier1', 'tier2']
        print("   → Checking Tier 1 (Daily) + Tier 2 (Weekly)")
    else:
        tiers_to_check = ['tier1']
        print("   → Checking Tier 1 (Daily) only")

    alerts = run_scan(tiers_to_check)
    generate_alert_report(alerts)

    print("\n" + "="*80)
    print("SCAN COMPLETE")
    print("="*80)
