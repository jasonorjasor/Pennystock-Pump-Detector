import yfinance as yf
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")  # Force non-GUI backend
import matplotlib.pyplot as plt
import os
from datetime import datetime
LOOKBACK = os.environ.get("LOOKBACK", "1y")  # '6mo', '1y', etc.
RUN_NAME = os.environ.get("RUN_NAME", f"{datetime.now():%Y-%m-%d_%H%M}_{LOOKBACK}")
RUN_DIR  = os.path.join("runs", RUN_NAME)
os.makedirs(RUN_DIR, exist_ok=True)

def backtest_signals(ticker, df):
    """
    STEP 1: Add 20-day future returns & drawdown metrics
    
    For each pump signal, this calculates:
    - Forward returns at 1, 5, 10, 20 days
    - Maximum drawdown in next 20 days
    - Days until bottom
    - Maximum gain (if it kept pumping)
    - Days until peak
    """
    
    signals = df[df['flag'] == True].copy()
    
    if len(signals) == 0:
        return None
    
    backtest_results = []
    
    for signal_date, signal_row in signals.iterrows():
        signal_idx = df.index.get_loc(signal_date)
        entry_price = signal_row['Close']
        
        # === FORWARD RETURNS ===
        forward_returns = {}
        
        for days in [1, 5, 10, 20]:
            future_idx = signal_idx + days
            
            if future_idx < len(df):
                future_price = df.iloc[future_idx]['Close']
                forward_return = (future_price - entry_price) / entry_price
                forward_returns[f'return_{days}d'] = forward_return
            else:
                forward_returns[f'return_{days}d'] = None
        
        # === MAX DRAWDOWN ===
        # Find worst drop in next 20 days
        max_drawdown = 0
        days_to_bottom = None
        
        future_window = df.iloc[signal_idx:min(signal_idx+21, len(df))]
        
        if len(future_window) > 1:
            drawdowns = (future_window['Close'] - entry_price) / entry_price
            max_drawdown = drawdowns.min()
            
            if max_drawdown < 0:
                days_to_bottom = drawdowns.idxmin()
                days_to_bottom = (days_to_bottom - signal_date).days
        
        # === TIME TO PEAK ===
        # Did it keep pumping before dumping?
        max_gain = 0
        days_to_peak = 0
        
        if len(future_window) > 1:
            gains = (future_window['Close'] - entry_price) / entry_price
            max_gain = gains.max()
            
            if max_gain > 0:
                days_to_peak = gains.idxmax()
                days_to_peak = (days_to_peak - signal_date).days
        
        # Compile all metrics
        result = {
            'ticker': ticker,
            'signal_date': signal_date,
            'entry_price': entry_price,
            'pump_score': signal_row['pump_score'],
            'volume': signal_row['Volume'],
            'vol_z': signal_row['vol_z'],
            'vol_ratio': signal_row['vol_ratio'],
            'signal_return': signal_row['return'],
            'gap_up': signal_row['gap_up'],
            'volatility': signal_row['volatility'],
            
            # Forward returns
            'return_1d': forward_returns.get('return_1d'),
            'return_5d': forward_returns.get('return_5d'),
            'return_10d': forward_returns.get('return_10d'),
            'return_20d': forward_returns.get('return_20d'),
            
            # Drawdown metrics
            'max_drawdown_20d': max_drawdown,
            'days_to_bottom': days_to_bottom,
            
            # Peak metrics
            'max_gain_20d': max_gain,
            'days_to_peak': days_to_peak,
        }
        
        backtest_results.append(result)
    
    return pd.DataFrame(backtest_results)


def auto_classify_signals(df):
    """
    Improved pump/legit classification logic
    """
    
    def classify_row(row):
        max_dd = row['max_drawdown_20d']
        r1 = row['return_1d']
        r5 = row['return_5d']
        r10 = row['return_10d']
        r20 = row['return_20d']
        days_to_bottom = row['days_to_bottom']
        
        # Missing data safety
        if pd.isna(max_dd) or pd.isna(r20):
            return 'insufficient_data'
        
        # ========================================
        # CONFIRMED PUMP PATTERNS
        # ========================================
        
        # Pattern 1: Immediate reversal (next day dump)
        fast_reversal = (not pd.isna(r1)) and (r1 < -0.10)
        
        # Pattern 2: Quick crash (within 5 days)
        quick_crash = (not pd.isna(r5)) and (r5 < -0.15)
        
        # Pattern 3: Deep drawdown
        deep_crash = max_dd < -0.20
        
        # Pattern 4: Fast bottom (crashed within 10 days)
        fast_bottom = (days_to_bottom is not None) and (days_to_bottom <= 10)
        
        if fast_reversal or quick_crash:
            return 'confirmed_pump'
        
        if deep_crash and fast_bottom:
            return 'confirmed_pump'
        
        # ========================================
        # LIKELY PUMP (Medium confidence)
        # ========================================
        
        if max_dd < -0.10:  # 10-20% crash range
            return 'likely_pump'
        
        # ========================================
        # LIKELY LEGIT (Sustained breakout)
        # ========================================
        
        # Must check if r5 and r10 exist before comparing
        has_early_data = (not pd.isna(r5)) and (not pd.isna(r10))
        
        if has_early_data:
            # Sustained gains: up at 5d, up at 10d, no crash
            sustained_rally = (r5 > 0.08 and r10 > 0.08 and max_dd > -0.10)
            
            # Strong sustained rally: big gains maintained
            strong_rally = (r5 > 0.15 and r20 > 0.15 and max_dd > -0.05)
            
            if sustained_rally or strong_rally:
                return 'likely_legit'
        
        # ========================================
        # UNCERTAIN (Everything else)
        # ========================================
        
        return 'uncertain'
    
    df['classification'] = df.apply(classify_row, axis=1)
    return df

def detect_pump_episodes(master):
    """
    Groups pump signals into "episodes" - coordinated pump campaigns
    """
    
    if master is None or len(master) == 0:
        return None, None, None
    
    print("\n" + "="*80)
    print("🔍 DETECTING PUMP EPISODES")
    print("="*80)
    
    # Convert signal_date to datetime
    master['signal_date'] = pd.to_datetime(master['signal_date'])
    
    # Sort by ticker and date
    df = master.sort_values(['ticker', 'signal_date']).copy()
    
    # Calculate days since last signal for same ticker
    df['days_since_last'] = df.groupby('ticker')['signal_date'].diff().dt.days
    
    # New episode starts if >7 days since last signal (or first signal for ticker)
    df['new_episode'] = (df['days_since_last'].isna()) | (df['days_since_last'] > 7)
    
    # Assign episode IDs
    df['episode_id'] = df.groupby('ticker')['new_episode'].cumsum()
    
    # Create unique episode identifier
    df['episode_key'] = df['ticker'] + '_E' + df['episode_id'].astype(str)
    
    # Episode statistics
    episodes = df.groupby('episode_key').agg({
        'ticker': 'first',
        'signal_date': ['min', 'max', 'count'],
        'pump_score': 'mean',
        'entry_price': 'mean',
        'max_drawdown_20d': 'mean',
        'return_20d': 'mean',
        'classification': lambda x: (x.isin(['confirmed_pump', 'likely_pump'])).sum()
    })
    
    # Flatten columns
    episodes.columns = ['ticker', 'start_date', 'end_date', 'signal_count', 
                       'avg_pump_score', 'avg_price', 'avg_drawdown', 
                       'avg_return_20d', 'pump_count']
    
    # Calculate duration
    episodes['duration_days'] = (episodes['end_date'] - episodes['start_date']).dt.days
    episodes['episode_pump_rate'] = (episodes['pump_count'] / episodes['signal_count'] * 100)
    
    # Keep episode_key as a column (don't drop it)
    episodes = episodes.reset_index()  # Changed from reset_index(drop=True)
    
    episodes = episodes.sort_values('pump_count', ascending=False)
    
    # Ensure directory exists
    signals_dir = os.path.join(RUN_DIR, "data", "signals_csv")
    os.makedirs(signals_dir, exist_ok=True)
    
    # Save episodes
    episodes.to_csv(os.path.join(signals_dir, "PUMP_EPISODES.csv"), index=False)
    
    print(f"\n Episode Summary:")
    print(f"  Total episodes: {len(episodes)}")
    print(f"  Single-signal: {(episodes['signal_count'] == 1).sum()}")
    print(f"  Multi-signal: {(episodes['signal_count'] > 1).sum()}")
    
    # Sustained campaigns
    sustained = episodes[episodes['signal_count'] >= 2]
    
    if len(sustained) > 0:
        print(f"\n SUSTAINED CAMPAIGNS (2+ signals in 7 days):")
        print(f"  Found {len(sustained)} campaigns")
        print(f"  Avg signals per campaign: {sustained['signal_count'].mean():.1f}")
        print(f"\n TOP 10 SUSTAINED CAMPAIGNS:")
        print("="*80)
        display_cols = ['ticker', 'start_date', 'signal_count', 'duration_days', 
                       'avg_pump_score', 'avg_drawdown', 'pump_count']
        print(sustained[display_cols].head(10).to_string(index=False))
    
    # Ticker frequency
    ticker_episodes = episodes.groupby('ticker').agg({
        'episode_key': 'count',
        'signal_count': 'sum',
        'pump_count': 'sum',
        'avg_drawdown': 'mean',
        'avg_price': 'mean'
    }).rename(columns={
        'episode_key': 'total_episodes',
        'signal_count': 'total_signals',
        'pump_count': 'total_pumps'
    })
    
    ticker_episodes['pump_rate'] = (ticker_episodes['total_pumps'] / 
                                    ticker_episodes['total_signals'] * 100)
    ticker_episodes['is_penny_stock'] = ticker_episodes['avg_price'] < 1.0
    ticker_episodes = ticker_episodes.sort_values('total_episodes', ascending=False)
    
    print(f"\n TICKER EPISODE FREQUENCY:")
    print("="*80)
    print(ticker_episodes.to_string())
    
    # High-risk tickers
    high_risk = ticker_episodes[ticker_episodes['total_episodes'] >= 3]
    
    if len(high_risk) > 0:
        print(f"\n  HIGH-RISK TICKERS (3+ pump episodes):")
        print("="*80)
        print(f"  These tickers are REPEATEDLY targeted!")
        print()
        for ticker in high_risk.index:
            total_eps = high_risk.loc[ticker, 'total_episodes']
            total_sigs = high_risk.loc[ticker, 'total_signals']
            pump_rate = high_risk.loc[ticker, 'pump_rate']
            avg_dd = high_risk.loc[ticker, 'avg_drawdown'] * 100
            
            print(f"  🚨 {ticker:6s}: {total_eps} episodes, {total_sigs} signals, "
                  f"{pump_rate:.0f}% pump rate, avg crash: {avg_dd:.1f}%")
    
    # Penny stock analysis
    penny_episodes = episodes[episodes['avg_price'] < 1.0]
    large_episodes = episodes[episodes['avg_price'] >= 1.0]
    
    print(f"\n PENNY STOCKS vs LARGER STOCKS:")
    print("="*80)
    
    if len(penny_episodes) > 0:
        penny_pump_pct = (penny_episodes['pump_count'].sum() / 
                         penny_episodes['signal_count'].sum() * 100)
        print(f"  Penny stocks (<$1): {len(penny_episodes)} episodes")
        print(f"    Pump rate: {penny_pump_pct:.1f}%")
        print(f"    Avg crash: {penny_episodes['avg_drawdown'].mean()*100:.1f}%")
    
    if len(large_episodes) > 0:
        large_pump_pct = (large_episodes['pump_count'].sum() / 
                         large_episodes['signal_count'].sum() * 100)
        print(f"\n  Larger stocks (≥$1): {len(large_episodes)} episodes")
        print(f"    Pump rate: {large_pump_pct:.1f}%")
        print(f"    Avg crash: {large_episodes['avg_drawdown'].mean()*100:.1f}%")
    
    print(f"\n Episode data saved to: {signals_dir}/PUMP_EPISODES.csv")
    
    #
    master_with_episodes = master.merge(
        df[['ticker', 'signal_date', 'episode_key']],
        on=['ticker', 'signal_date'],
        how='left'
    )
    
    # Save enhanced master
    master_with_episodes.to_csv(os.path.join(signals_dir, "MASTER_TRUTH_WITH_EPISODES.csv"), index=False)


    return master_with_episodes, episodes, ticker_episodes

def analyze_ticker(ticker):
    """
    Main analysis function - now integrated with backtesting
    """
    print(f"\n=== Analyzing {ticker} ===")

    # Download data
    df = yf.download(ticker, period=LOOKBACK, interval="1d")


    # Updated directory structure
    img_dir = os.path.join(RUN_DIR, "data/images", ticker)

    os.makedirs(img_dir, exist_ok=True)

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.droplevel(1)

    if df.empty:
        print(f"No data returned for {ticker}. Skipping.")
        return None

    # === FEATURE ENGINEERING ===
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
    df['momentum'] = df['Close'].rolling(5).mean() / \
                     (df['Close'].rolling(20).mean() + 1e-9) - 1

    # === PUMP SCORING WITH SYNERGY ===
    df['pump_score'] = 0
    df.loc[df['vol_z'] > 2, 'pump_score'] += 20
    df.loc[df['vol_z'] > 3, 'pump_score'] += 10
    df.loc[df['vol_ratio'] > 3, 'pump_score'] += 15
    df.loc[df['return'] > 0.1, 'pump_score'] += 20
    df.loc[df['return'] > 0.2, 'pump_score'] += 10
    df.loc[df['price_z'] > 2, 'pump_score'] += 15
    df.loc[df['gap_up'] > 0.05, 'pump_score'] += 10
    df.loc[df['volatility'] > 0.1, 'pump_score'] += 10
    
    synergy_condition = (df['vol_trend'] > 1.2) & (df['return'] > 0.1)
    df.loc[synergy_condition, 'pump_score'] += 10
    
    df['flag'] = df['pump_score'] > 50

    # === TWO-PANEL VISUALIZATION ===
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 8), 
                                     sharex=True, 
                                     gridspec_kw={'height_ratios': [2, 1]})
    
    ax1.plot(df.index, df['Close'], label="Close Price", 
             linewidth=2, color='#2E86DE')
    ax1.plot(df.index, df['Close'].rolling(20).mean(), 
             label="20-day MA", linestyle='--', alpha=0.7, color='#A29BFE')

    flags = df[df['flag'] == True]
    
    if len(flags) > 0:
        for idx, row in flags.iterrows():
            ax1.scatter(idx, row['Close'], marker='o', color='#FF6B6B', 
                       s=50, zorder=5, edgecolors='darkred', linewidths=2)
            
            score_text = f"🚨{int(row['pump_score'])}"
            ax1.text(idx, row['Close'], score_text, 
                    fontsize=9, ha='center', va='bottom',
                    bbox=dict(boxstyle='round,pad=0.3', 
                             facecolor='red', alpha=0.7, edgecolor='darkred'),
                    color='white', fontweight='bold')

    ax1.set_title(f"Pump Detection Analysis: {ticker}", 
                  fontsize=15, fontweight='bold', pad=15)
    ax1.set_ylabel("Price ($)", fontsize=12, fontweight='bold')
    ax1.legend(loc='upper left', framealpha=0.9)
    ax1.grid(alpha=0.3, linestyle='--')
    
    ax2.plot(df.index, df['pump_score'], 
             linewidth=2, color='#6C5CE7', label='Pump Score')
    ax2.fill_between(df.index, 0, df['pump_score'], 
                     alpha=0.3, color='#6C5CE7')
    ax2.axhline(y=50, color='#FF6B6B', linestyle='--', 
                linewidth=2, label='Pump Threshold (50)', alpha=0.8)
    
    for idx in flags.index:
        ax2.axvline(x=idx, color='#FF6B6B', alpha=0.3, linewidth=1.5)
    
    ax2.set_xlabel("Date", fontsize=12, fontweight='bold')
    ax2.set_ylabel("Pump Score", fontsize=12, fontweight='bold')
    ax2.set_ylim(0, max(100, df['pump_score'].max() + 10))
    ax2.legend(loc='upper left', framealpha=0.9)
    ax2.grid(alpha=0.3, linestyle='--')
    
    plt.tight_layout()
    plt.savefig(f"{img_dir}/{ticker}_two_panel_analysis.png", dpi=300, bbox_inches='tight')
    plt.close()

    # === VOLUME CHART ===
    df_plot = df[df['Volume'] > 0].copy()
    plt.figure(figsize=(14, 4))
    plt.bar(df_plot.index, df_plot['Volume'], width=1.0, alpha=0.7, color='#00B894')
    plt.yscale("log")
    plt.xticks(rotation=45, ha='right')
    plt.title(f"Volume Analysis: {ticker}", fontsize=14, fontweight='bold')
    plt.xlabel("Date", fontsize=12)
    plt.ylabel("Volume (log scale)", fontsize=12)
    plt.grid(axis='y', linestyle='--', alpha=0.5)
    plt.tight_layout()
    plt.savefig(f"{img_dir}/{ticker}_volume.png", dpi=300, bbox_inches='tight')
    plt.close()

    # === SAVE SIGNALS CSV (UPDATED PATH) ===
    signals_dir = os.path.join(RUN_DIR, "data/signals_csv", ticker)
    os.makedirs(signals_dir, exist_ok=True)

    df_export = df.reset_index()
    df_export.to_csv(f"{signals_dir}/signals.csv", index=False)



    
    # === RUN BACKTEST ===
    backtest_df = backtest_signals(ticker, df)
    
    if backtest_df is not None and len(backtest_df) > 0:
        # STEP 2: Auto-classify signals
        backtest_df = auto_classify_signals(backtest_df)
        
        # Save individual ticker backtest (UPDATED PATH)
        backtest_df.to_csv(f"{signals_dir}/backtest.csv", index=False)
        print(f"Backtest results saved to {signals_dir}/{ticker}_backtest.csv")
        
        # Show classification breakdown
        print(f"\n Signal Classification for {ticker}:")
        class_counts = backtest_df['classification'].value_counts()
        for cls, count in class_counts.items():
            pct = count / len(backtest_df) * 100
            print(f"  {cls:20s}: {count:2d} ({pct:5.1f}%)")
        
        # Show key statistics
        if len(backtest_df) > 0:
            avg_ret_20d = backtest_df['return_20d'].mean() * 100
            avg_max_dd = backtest_df['max_drawdown_20d'].mean() * 100
            print(f"\n Performance Metrics:")
            print(f"  Avg 20-day return: {avg_ret_20d:+.2f}%")
            print(f"  Avg max drawdown:  {avg_max_dd:.2f}%")
    else:
        print("✓ No pump signals detected")
        backtest_df = None
    
    return backtest_df


def create_master_truth_csv(tickers):
    """
    STEP 4: Combine all backtest results into one master CSV
    
    This creates the "ground truth" dataset with:
    - All pump signals
    - Their features (volume, price, etc.)
    - Their outcomes (forward returns, drawdowns)
    - Auto-classifications
    """
    
    signals_dir = os.path.join(RUN_DIR, "data/signals_csv")
    all_backtests = []
    
    for ticker in tickers:
        backtest_path = f"{signals_dir}/{ticker}/backtest.csv"
        
        if os.path.exists(backtest_path):
            df = pd.read_csv(backtest_path)
            if len(df) > 0:
                all_backtests.append(df)
    
    if not all_backtests:
        print("No backtest results found.")
        return None
    
    # Combine all backtests
    master = pd.concat(all_backtests, ignore_index=True)
    
    # Sort by pump score (highest first)
    master = master.sort_values('pump_score', ascending=False)
    
    # STEP 4: Save master truth CSV (UPDATED PATH)
    master.to_csv(f"{signals_dir}/MASTER_TRUTH.csv", index=False)
    

    print("MASTER TRUTH DATASET CREATED")

    
    # === OVERALL STATISTICS ===
    total_signals = len(master)
    
    print(f"\n Dataset Overview:")
    print(f"  Total pump signals: {total_signals}")
    print(f"  Unique tickers: {master['ticker'].nunique()}")
    print(f"  Date range: {master['signal_date'].min()} to {master['signal_date'].max()}")
    
    # === CLASSIFICATION BREAKDOWN ===
    print(f"\n Classification Breakdown:")
    class_counts = master['classification'].value_counts()
    for cls, count in class_counts.items():
        pct = count / total_signals * 100
        print(f"  {cls:20s}: {count:3d} ({pct:5.1f}%)")
    
    # === PERFORMANCE METRICS ===
    print(f"\n Performance Metrics (All Signals):")
    
    # Filter out signals with insufficient data
    valid_signals = master[master['classification'] != 'insufficient_data']
    
    if len(valid_signals) > 0:
        avg_return_1d = valid_signals['return_1d'].mean() * 100
        avg_return_5d = valid_signals['return_5d'].mean() * 100
        avg_return_10d = valid_signals['return_10d'].mean() * 100
        avg_return_20d = valid_signals['return_20d'].mean() * 100
        avg_max_drawdown = valid_signals['max_drawdown_20d'].mean() * 100
        
        print(f"  Avg return  1-day:  {avg_return_1d:+.2f}%")
        print(f"  Avg return  5-day:  {avg_return_5d:+.2f}%")
        print(f"  Avg return 10-day:  {avg_return_10d:+.2f}%")
        print(f"  Avg return 20-day:  {avg_return_20d:+.2f}%")
        print(f"  Avg max drawdown:   {avg_max_drawdown:.2f}%")
    
    # === PUMP VS LEGIT COMPARISON ===
    confirmed_pumps = master[master['classification'] == 'confirmed_pump']
    likely_legit = master[master['classification'] == 'likely_legit']
    
    if len(confirmed_pumps) > 0:
        print(f"\n Confirmed Pumps (n={len(confirmed_pumps)}):")
        print(f"  Avg pump score: {confirmed_pumps['pump_score'].mean():.1f}")
        print(f"  Avg 20d return: {confirmed_pumps['return_20d'].mean()*100:+.2f}%")
        print(f"  Avg max drawdown: {confirmed_pumps['max_drawdown_20d'].mean()*100:.2f}%")
    
    if len(likely_legit) > 0:
        print(f"\n Likely Legitimate (n={len(likely_legit)}):")
        print(f"  Avg pump score: {likely_legit['pump_score'].mean():.1f}")
        print(f"  Avg 20d return: {likely_legit['return_20d'].mean()*100:+.2f}%")
        print(f"  Avg max drawdown: {likely_legit['max_drawdown_20d'].mean()*100:.2f}%")
    
    # === TOP 10 CONFIRMED PUMPS ===
    if len(confirmed_pumps) > 0:
        print(f"\n TOP 10 CONFIRMED PUMPS (Worst Dumps):")
        print("="*80)
        top_pumps = confirmed_pumps.nsmallest(10, 'max_drawdown_20d')
        display_cols = ['ticker', 'signal_date', 'pump_score', 'signal_return', 
                       'return_20d', 'max_drawdown_20d']
        print(top_pumps[display_cols].to_string(index=False))
    
    # === TOP 10 LIKELY LEGIT ===
    if len(likely_legit) > 0:
        print(f"\n TOP 10 LIKELY LEGITIMATE MOVES:")
        print("="*80)
        top_legit = likely_legit.nlargest(10, 'return_20d')
        display_cols = ['ticker', 'signal_date', 'pump_score', 'signal_return', 
                       'return_20d', 'max_drawdown_20d']
        print(top_legit[display_cols].to_string(index=False))
    
    # === DETECTOR PERFORMANCE ===
    print(f"\n Detector Performance:")
    
    pump_signals = master[master['classification'].isin(['confirmed_pump', 'likely_pump'])]
    pump_rate = len(pump_signals) / total_signals * 100
    
    print(f"  Pump detection rate: {pump_rate:.1f}%")
    print(f"  (Goal: >40% for good detector)")
    
    if pump_rate > 50:
        print(f"   EXCELLENT - Your detector is very accurate!")
    elif pump_rate > 40:
        print(f"   GOOD - Your detector works well")
    elif pump_rate > 30:
        print(f"   FAIR - Detector works but could be improved")
    else:
        print(f"   NEEDS WORK - Detector needs tuning")
    

    print(f"   {len(master)} total signals with full backtest data")
    
    return master


# ============================================
# MAIN EXECUTION
# ============================================

if __name__ == "__main__":
    tickers = [
        "FEMY","NAKA","MBRX","AGL","CHGG","IXHL","MODD","PSNY","SHOT","IPSC",
        "AIRE","OPI","NWTN","SGMO","ACET","PPBT","AZI","MOBX","PCSA","CENN",
        "ARBK","ICCM","LBGJ","PRPL","VRME","ATCH","ORIS","PFSA","HBIO","XHLD",
        "VSEE","EHGO"
    ]
    
    print("Starting Complete Pump Detection System")
    print("="*80)
    
    # Analyze each ticker
    for t in tickers:
        analyze_ticker(t)
    
    # Create master truth CSV
    master = create_master_truth_csv(tickers)
    
    # Detect pump episodes
    if master is not None:
        master_with_episodes, episodes, ticker_episodes = detect_pump_episodes(master)
    
    print("\n" + "="*80)
    print("COMPLETE ANALYSIS FINISHED")
    print("="*80)