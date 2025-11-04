import yfinance as yf
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import os

def analyze_ticker(ticker):
    """
    Analyzes a single ticker for pump-and-dump patterns.
    NOW WITH: Annotated markers, two-panel plots, and synergy bonus
    """
    print(f"\n=== Analyzing {ticker} ===")

    # ============================================
    # STEP 1: DATA COLLECTION
    # ============================================
    df = yf.download(ticker, period="6mo", interval="1d")

    img_dir = f"data/images/{ticker}"
    os.makedirs(img_dir, exist_ok=True)

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.droplevel(1)

    if df.empty:
        print(f"No data returned for {ticker}. Skipping.")
        return

    # ============================================
    # STEP 2: FEATURE ENGINEERING
    # ============================================
    
    # Volume features
    df['vol_z'] = (df['Volume'] - df['Volume'].rolling(20).mean()) / \
                  (df['Volume'].rolling(20).std() + 1e-9)
    df['vol_ratio'] = df['Volume'] / (df['Volume'].rolling(20).mean() + 1e-9)
    df['vol_trend'] = df['Volume'].rolling(5).mean() / \
                      (df['Volume'].rolling(20).mean() + 1e-9)

    # Price features
    df['return'] = df['Close'].pct_change()
    df['price_z'] = (df['return'] - df['return'].rolling(20).mean()) / \
                    (df['return'].rolling(20).std() + 1e-9)
    df['gap_up'] = (df['Open'] - df['Close'].shift(1)) / (df['Close'].shift(1) + 1e-9)
    df['volatility'] = (df['High'] - df['Low']) / (df['Close'] + 1e-9)
    df['momentum'] = df['Close'].rolling(5).mean() / \
                     (df['Close'].rolling(20).mean() + 1e-9) - 1

    # ============================================
    # STEP 3: PUMP SCORING SYSTEM (WITH SYNERGY)
    # ============================================
    
    df['pump_score'] = 0

    # Volume scoring
    df.loc[df['vol_z'] > 2, 'pump_score'] += 20
    df.loc[df['vol_z'] > 3, 'pump_score'] += 10
    df.loc[df['vol_ratio'] > 3, 'pump_score'] += 15

    # Price scoring
    df.loc[df['return'] > 0.1, 'pump_score'] += 20
    df.loc[df['return'] > 0.2, 'pump_score'] += 10
    df.loc[df['price_z'] > 2, 'pump_score'] += 15

    # Pattern scoring
    df.loc[df['gap_up'] > 0.05, 'pump_score'] += 10
    df.loc[df['volatility'] > 0.1, 'pump_score'] += 10

    # 🆕 SYNERGY BONUS: Volume + Price moving together
    # This catches coordinated pump behavior
    synergy_condition = (df['vol_trend'] > 1.2) & (df['return'] > 0.1)
    df.loc[synergy_condition, 'pump_score'] += 10
    
    # Flag as pump if score exceeds threshold
    df['flag'] = df['pump_score'] > 50

    # ============================================
    # STEP 4: 🆕 TWO-PANEL VISUALIZATION
    # ============================================
    
    # Create figure with 2 subplots (shared x-axis)
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 8), 
                                     sharex=True, 
                                     gridspec_kw={'height_ratios': [2, 1]})
    
    # --- TOP PANEL: PRICE CHART ---
    ax1.plot(df.index, df['Close'], label="Close Price", 
             linewidth=2, color='#2E86DE')
    ax1.plot(df.index, df['Close'].rolling(20).mean(), 
             label="20-day MA", linestyle='--', alpha=0.7, color='#A29BFE')

    # Get pump signals
    flags = df[df['flag'] == True]
    
    # 🆕 ANNOTATED MARKERS: Show pump score on each signal
# Annotated pump markers with staggered labels
    if len(flags) > 0:
        for i, (idx, row) in enumerate(flags.iterrows()):
            # Red dot marker
            ax1.scatter(idx, row['Close'], marker='o', color='#FF6B6B', 
                        s=150, zorder=5, edgecolors='darkred', linewidths=2)
            
            # Alternate text position (above/below the dot)
            y_offset = 1.03 if i % 2 == 0 else 0.97
            score_text = f"🚨{int(row['pump_score'])}"
            ax1.text(idx, row['Close'] * y_offset, score_text, 
                    fontsize=9, ha='center', 
                    bbox=dict(boxstyle='round,pad=0.3',
                            facecolor='red', alpha=0.75, edgecolor='darkred'),
                    color='white', fontweight='bold')


    ax1.set_title(f"Pump Detection Analysis: {ticker}", 
                  fontsize=15, fontweight='bold', pad=15)
    ax1.set_ylabel("Price ($)", fontsize=12, fontweight='bold')
    ax1.legend(loc='upper left', framealpha=0.9)
    ax1.grid(alpha=0.3, linestyle='--')
    
    # --- BOTTOM PANEL: PUMP SCORE TREND ---
    # Plot the raw pump score (NOT smoothed for signal integrity)
    ax2.plot(df.index, df['pump_score'], 
             linewidth=2, color='#6C5CE7', label='Pump Score')
    
    # Fill area under the curve
    ax2.fill_between(df.index, 0, df['pump_score'], 
                     alpha=0.3, color='#6C5CE7')
    
    # Highlight pump threshold line
    ax2.axhline(y=50, color='#FF6B6B', linestyle='--', 
                linewidth=2, label='Pump Threshold (50)', alpha=0.8)
    
    # Mark actual pump days with vertical lines
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

    # ============================================
    # STEP 5: VOLUME CHART (SEPARATE)
    # ============================================
    
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

    # ============================================
    # STEP 6: SAVE DATA
    # ============================================
    
    signals_dir = "data/signals_csv"
    os.makedirs(signals_dir, exist_ok=True)
    df.reset_index().to_csv(f"{signals_dir}/{ticker}_signals.csv", index=False)


    # ============================================
    # STEP 7: CONSOLE OUTPUT
    # ============================================
    
    print(f"✅ Saved charts to {img_dir}/")
    print(f"✅ Saved data to {signals_dir}/{ticker}_signals.csv")
    
    if len(flags) > 0:
        print(f"🚨 Found {len(flags)} pump signal(s):")
        print(flags[['Close', 'Volume', 'return', 'vol_z', 'pump_score']].to_string())
        
        # Show synergy detections
        synergy_flags = flags[synergy_condition.loc[flags.index]]
        if len(synergy_flags) > 0:
            print(f"⚡ {len(synergy_flags)} signal(s) had SYNERGY BONUS (vol+price spike)")
    else:
        print("✓ No pump signals detected")


def create_summary_report(tickers):
    """Aggregates pump signals across all tickers."""
    print("\n" + "="*70)
    print("CREATING SUMMARY REPORT")
    print("="*70)
    
    all_signals = []
    
    for ticker in tickers:
        csv_path = f"data/signals_csv/{ticker}_signals.csv"
        
        if os.path.exists(csv_path):
            df = pd.read_csv(csv_path)
            df['ticker'] = ticker
            flags = df[df['flag'] == True]
            
            if len(flags) > 0:
                all_signals.append(flags)
    
    if all_signals:
        summary = pd.concat(all_signals, ignore_index=True)
        summary = summary.sort_values('pump_score', ascending=False)
        summary.to_csv("data/signals_csv/ALL_SIGNALS_SUMMARY.csv", index=False)
        
        print("\n🚨 TOP 10 PUMP SIGNALS (Ranked by Score):")
        print("="*70)
        
        top_signals = summary[['ticker', 'Date', 'Close', 'Volume', 
                               'return', 'vol_z', 'pump_score']].head(10)
        print(top_signals.to_string(index=False))
        
        print(f"\n✅ Full report saved to data/signals_csv/ALL_SIGNALS_SUMMARY.csv")
        print(f"📊 Total signals found: {len(summary)}")
        print(f"📊 Tickers with signals: {summary['ticker'].nunique()}")
        
        # Show synergy statistics
        if 'vol_trend' in summary.columns:
            synergy_count = ((summary['vol_trend'] > 1.2) & (summary['return'] > 0.1)).sum()
            print(f"⚡ Signals with synergy bonus: {synergy_count} ({synergy_count/len(summary)*100:.1f}%)")
        
        return summary
    else:
        print("❌ No pump signals found across any tickers.")
        return None


# ============================================
# MAIN EXECUTION
# ============================================

if __name__ == "__main__":
    tickers = ["DFLI", "BYND", "PCSA", "AAPL", "BITF", "CIGL", "NVDA", "SES", "ONMD"]
    
    print("🚀 Starting Enhanced Pump & Dump Detection System")
    print("="*70)
    print("NEW FEATURES:")
    print("  ✓ Annotated pump score markers (🚨XX)")
    print("  ✓ Two-panel analysis (Price + Pump Score)")
    print("  ✓ Synergy bonus detection (Vol + Price together)")
    print("="*70)
    
    for t in tickers:
        analyze_ticker(t)
    
    summary = create_summary_report(tickers)
    
    print("\n" + "="*70)
    print("✅ ANALYSIS COMPLETE")
    print("="*70)