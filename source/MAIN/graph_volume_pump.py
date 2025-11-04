# import yfinance as yf
# import pandas as pd
# import numpy as np
# import matplotlib.pyplot as plt
# import os

# def analyze_ticker(ticker):
#     print(f"\n=== Analyzing {ticker} ===")

#     # Fetch data
#     df = yf.download(ticker, period="6mo", interval="1d")

#     # Create image directory for this ticker
#     img_dir = f"images/{ticker}"
#     os.makedirs(img_dir, exist_ok=True)

#     # Fix MultiIndex issues
#     if isinstance(df.columns, pd.MultiIndex):
#         df.columns = df.columns.droplevel(1)

#     # Safety check
#     if df.empty:
#         print(f"No data returned for {ticker}. Skipping.")
#         return

#     # Feature engineering
#     df['vol_z'] = (df['Volume'] - df['Volume'].rolling(20).mean()) / \
#                   (df['Volume'].rolling(20).std() + 1e-9)
#     df['return'] = df['Close'].pct_change()
#     df['flag'] = (df['vol_z'] > 3) & (df['return'] > 0.1)

#     # === PRICE CHART ===
#     plt.figure(figsize=(12,6))
#     plt.plot(df.index, df['Close'], label="Close Price")
#     plt.plot(df.index, df['Close'].rolling(20).mean(), label="20-day MA", linestyle='--')

#     # Pump markers + legend entry
#     flags = df[df['flag']]
#     plt.scatter([], [], marker='o', color='red', s=100, label="Pump Signal")  # legend handle

#     for idx, row in flags.iterrows():
#         plt.scatter(idx, row['Close'], marker='o', color='red', s=100, zorder=5)
#         plt.text(idx, row['Close'], "🚨", fontsize=12, ha='center')

#     plt.title(f"Pump-like Signals for {ticker}")
#     plt.legend()
#     plt.xlabel("Date")
#     plt.ylabel("Price")
#     plt.tight_layout()
#     plt.savefig(f"{img_dir}/{ticker}_pump_signal.png", dpi=300)
#     plt.close()

#     # === VOLUME CHART ===
#     df_plot = df[df['Volume'] > 0].copy()
#     plt.figure(figsize=(12,4))
#     plt.bar(df_plot.index, df_plot['Volume'], width=1.0)
#     plt.yscale("log")
#     plt.xticks(rotation=45, ha='right')
#     plt.title(f"Volume for {ticker}")
#     plt.xlabel("Date")
#     plt.ylabel("Volume (log scale)")
#     plt.grid(axis='y', linestyle='--', alpha=0.5)
#     plt.tight_layout()
#     plt.savefig(f"{img_dir}/{ticker}_volume.png", dpi=300)
#     plt.close()

#     print(f"✅ Saved charts to {img_dir}/")
#     # Save signals to CSV
#     signals_dir = "signals_csv"
#     os.makedirs(signals_dir, exist_ok=True)
#     df.to_csv(f"{signals_dir}/{ticker}_signals.csv", index=False)


# # Run for multiple tickers
# for t in ["DFLI", "BYND", "PCSA", "AAPL", "BITF", "CIGL", "NVDA", "SES", "YYAI"]:
#     analyze_ticker(t)


import yfinance as yf
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import os

def analyze_ticker(ticker):

    print(f"\n=== Analyzing {ticker} ===")


    # STEP 1: DATA COLLECTION
    # Download 6 months of daily stock data from Yahoo Finance
    df = yf.download(ticker, period="6mo", interval="1d")

    # Create a folder to save images for this specific ticker
    img_dir = f"images/{ticker}"
    os.makedirs(img_dir, exist_ok=True)

    # Fix MultiIndex issues that yfinance sometimes returns
    # (yfinance can return columns like ('Close', 'AAPL') instead of just 'Close')
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.droplevel(1)

    # Safety check: if no data was returned, skip this ticker
    if df.empty:
        print(f"No data returned for {ticker}. Skipping.")
        return

    # STEP 2: FEATURE ENGINEERING (BASIC)

    # --- VOLUME FEATURES ---
    
    # vol_z: Volume Z-Score
    # Measures how unusual today's volume is compared to the past 20 days
    # Z-score > 3 means volume is 3 standard deviations above average (very unusual)
    # Formula: (today's volume - 20-day average) / 20-day std deviation
    df['vol_z'] = (df['Volume'] - df['Volume'].rolling(20).mean()) / \
                  (df['Volume'].rolling(20).std() + 1e-9)  # +1e-9 prevents division by zero

    # vol_ratio: Volume Ratio
    # Simple ratio: today's volume / 20-day average volume
    # vol_ratio > 3 means today's volume is 3x normal
    df['vol_ratio'] = df['Volume'] / (df['Volume'].rolling(20).mean() + 1e-9)

    # vol_trend: Volume Trend/Acceleration
    # Compares recent volume (5-day avg) to longer-term volume (20-day avg)
    # > 1.0 means volume is accelerating (getting higher recently)
    df['vol_trend'] = df['Volume'].rolling(5).mean() / \
                      (df['Volume'].rolling(20).mean() + 1e-9)

    # --- PRICE FEATURES ---
    
    # return: Daily Price Return
    # Percentage change in closing price from yesterday to today
    # 0.1 = 10% gain, -0.05 = 5% loss
    df['return'] = df['Close'].pct_change()

    # price_z: Price Return Z-Score
    # Measures how unusual today's price move is compared to the past 20 days
    # Similar to vol_z but for price changes
    df['price_z'] = (df['return'] - df['return'].rolling(20).mean()) / \
                    (df['return'].rolling(20).std() + 1e-9)

    # gap_up: Opening Gap
    # Measures if stock opened significantly higher than previous close
    # Pumps often gap up at the open due to pre-market hype
    # 0.05 = opened 5% higher than yesterday's close
    df['gap_up'] = (df['Open'] - df['Close'].shift(1)) / (df['Close'].shift(1) + 1e-9)

    # volatility: Intraday Volatility
    # Measures how much the price swung during the day
    # (High - Low) / Close gives you the range as a percentage
    # High volatility often accompanies pumps
    df['volatility'] = (df['High'] - df['Low']) / (df['Close'] + 1e-9)

    # momentum: Price Momentum
    # Compares short-term trend (5-day MA) to longer-term trend (20-day MA)
    # > 0 means stock is trending up recently
    # Pumps show strong positive momentum
    df['momentum'] = df['Close'].rolling(5).mean() / \
                     (df['Close'].rolling(20).mean() + 1e-9) - 1


    # STEP 3: PUMP SCORING SYSTEM

    
    # Create a pump score (0-100 scale)
    # Higher score = more pump-like characteristics
    df['pump_score'] = 0

    # Add points for unusual volume (20 pts base, +10 bonus for extreme)
    df.loc[df['vol_z'] > 2, 'pump_score'] += 20      # Volume 2+ std devs above normal
    df.loc[df['vol_z'] > 3, 'pump_score'] += 10      # Extreme volume (3+ std devs)

    # Add points for price gains
    df.loc[df['return'] > 0.1, 'pump_score'] += 20   # 10%+ gain
    df.loc[df['return'] > 0.2, 'pump_score'] += 10   # 20%+ gain (bonus)

    # Add points for unusual price movement
    df.loc[df['price_z'] > 2, 'pump_score'] += 15    # Price move 2+ std devs

    # Add points for gap ups (pre-market hype indicator)
    df.loc[df['gap_up'] > 0.05, 'pump_score'] += 10  # 5%+ opening gap

    # Add points for high intraday volatility
    df.loc[df['volatility'] > 0.1, 'pump_score'] += 10  # 10%+ daily range

    # Add points for extreme volume ratio
    df.loc[df['vol_ratio'] > 3, 'pump_score'] += 15  # Volume 3x+ normal

    # FLAG: Mark as pump if score exceeds threshold
    # Score > 50 means multiple red flags are present
    df['flag'] = df['pump_score'] > 50

    # STEP 4: VISUALIZATION - PRICE CHART

    plt.figure(figsize=(12,6))
    
    # Plot the closing price as a line
    plt.plot(df.index, df['Close'], label="Close Price", linewidth=2)
    
    # Plot 20-day moving average as a dashed line
    # This shows the "normal" price trend
    plt.plot(df.index, df['Close'].rolling(20).mean(), 
             label="20-day MA", linestyle='--', alpha=0.7)

    # Mark pump signals on the chart
    flags = df[df['flag'] == True]  # Get all days flagged as pumps
    
    # Create a legend entry for pump signals (without plotting yet)
    plt.scatter([], [], marker='o', color='red', s=100, label="Pump Signal")

    # Plot each pump signal as a red dot with an alert emoji
    for idx, row in flags.iterrows():
        plt.scatter(idx, row['Close'], marker='o', color='red', s=100, zorder=5)
        plt.text(idx, row['Close'], "🚨", fontsize=12, ha='center')

    plt.title(f"Pump-like Signals for {ticker}", fontsize=14, fontweight='bold')
    plt.legend()
    plt.xlabel("Date")
    plt.ylabel("Price ($)")
    plt.grid(alpha=0.3)
    plt.tight_layout()
    
    # Save the chart as a high-resolution PNG
    plt.savefig(f"{img_dir}/{ticker}_pump_signal.png", dpi=300)
    plt.close()  # Close to free memory

    # STEP 5: VISUALIZATION - VOLUME CHART

    
    # Filter out days with zero volume (avoids log scale issues)
    df_plot = df[df['Volume'] > 0].copy()
    
    plt.figure(figsize=(12,4))
    
    # Bar chart of volume
    plt.bar(df_plot.index, df_plot['Volume'], width=1.0, alpha=0.7)
    
    # Use log scale for y-axis (volume can vary by orders of magnitude)
    plt.yscale("log")
    
    plt.xticks(rotation=45, ha='right')
    plt.title(f"Volume for {ticker}", fontsize=14, fontweight='bold')
    plt.xlabel("Date")
    plt.ylabel("Volume (log scale)")
    plt.grid(axis='y', linestyle='--', alpha=0.5)
    plt.tight_layout()
    
    # Save volume chart
    plt.savefig(f"{img_dir}/{ticker}_volume.png", dpi=300)
    plt.close()

    # STEP 6: SAVE RAW DATA TO CSV
    
    # Save all calculated features to a CSV file
    # This lets us analyze the data later or build a dashboard
    signals_dir = "signals_csv"
    os.makedirs(signals_dir, exist_ok=True)
    
    # Reset index so Date becomes a column (easier to read in Excel/CSV)
    df_export = df.reset_index()
    df_export.to_csv(f"{signals_dir}/{ticker}_signals.csv", index=False)

    print(f"✅ Saved charts to {img_dir}/")
    print(f"✅ Saved data to {signals_dir}/{ticker}_signals.csv")
    
    # Print pump signals found (if any)
    if len(flags) > 0:
        print(f"🚨 Found {len(flags)} pump signal(s):")
        print(flags[['Close', 'Volume', 'return', 'pump_score']].to_string())


def create_summary_report(tickers):

    print("\n" + "="*60)
    print("CREATING SUMMARY REPORT")
    print("="*60)
    
    all_signals = []
    
    # Loop through each ticker and load its signals
    for ticker in tickers:
        csv_path = f"signals_csv/{ticker}_signals.csv"
        
        if os.path.exists(csv_path):
            df = pd.read_csv(csv_path)
            df['ticker'] = ticker  # Add ticker column so we know which stock
            
            # Keep only days that were flagged as pumps
            flags = df[df['flag'] == True]
            
            if len(flags) > 0:
                all_signals.append(flags)
    
    # Combine all signals into one big DataFrame
    if all_signals:
        summary = pd.concat(all_signals, ignore_index=True)
        
        # Sort by pump_score (highest scores first)
        summary = summary.sort_values('pump_score', ascending=False)
        
        # Save master summary
        summary.to_csv("signals_csv/ALL_SIGNALS_SUMMARY.csv", index=False)
        
        print("\n🚨 TOP 10 PUMP SIGNALS (Ranked by Score):")
        print("="*60)
        
        # Display the top 10 most suspicious pump days
        top_signals = summary[['ticker', 'Date', 'Close', 'Volume', 
                               'return', 'vol_z', 'pump_score']].head(10)
        print(top_signals.to_string(index=False))
        
        print(f"\n✅ Full report saved to signals_csv/ALL_SIGNALS_SUMMARY.csv")
        print(f"Total signals found: {len(summary)}")
        
        return summary
    else:
        print("No pump signals found across any tickers.")
        return None

# MAIN EXECUTION


if __name__ == "__main__":
    # List of tickers to analyze
    tickers = ["DFLI", "BYND", "PCSA", "AAPL", "BITF", "CIGL", "NVDA", "SES"]
    
    print("🚀 Starting Pump & Dump Detection System")
    print("="*60)
    
    for t in tickers:
        analyze_ticker(t)
    
    # Create the master summary report
    summary = create_summary_report(tickers)
    
    print("\n" + "="*60)
    print("✅ ANALYSIS COMPLETE")
    print("="*60)