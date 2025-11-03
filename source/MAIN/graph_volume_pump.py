import yfinance as yf
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import os

def analyze_ticker(ticker):
    print(f"\n=== Analyzing {ticker} ===")

    # Fetch data
    df = yf.download(ticker, period="6mo", interval="1d")

    # Create image directory for this ticker
    img_dir = f"images/{ticker}"
    os.makedirs(img_dir, exist_ok=True)

    # Fix MultiIndex issues
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.droplevel(1)

    # Safety check
    if df.empty:
        print(f"No data returned for {ticker}. Skipping.")
        return

    # Feature engineering
    df['vol_z'] = (df['Volume'] - df['Volume'].rolling(20).mean()) / \
                  (df['Volume'].rolling(20).std() + 1e-9)
    df['return'] = df['Close'].pct_change()
    df['flag'] = (df['vol_z'] > 3) & (df['return'] > 0.1)

    # === PRICE CHART ===
    plt.figure(figsize=(12,6))
    plt.plot(df.index, df['Close'], label="Close Price")
    plt.plot(df.index, df['Close'].rolling(20).mean(), label="20-day MA", linestyle='--')

    # Pump markers + legend entry
    flags = df[df['flag']]
    plt.scatter([], [], marker='o', color='red', s=100, label="Pump Signal")  # legend handle

    for idx, row in flags.iterrows():
        plt.scatter(idx, row['Close'], marker='o', color='red', s=100, zorder=5)
        plt.text(idx, row['Close'], "🚨", fontsize=12, ha='center')

    plt.title(f"Pump-like Signals for {ticker}")
    plt.legend()
    plt.xlabel("Date")
    plt.ylabel("Price")
    plt.tight_layout()
    plt.savefig(f"{img_dir}/{ticker}_pump_signal.png", dpi=300)
    plt.close()

    # === VOLUME CHART ===
    df_plot = df[df['Volume'] > 0].copy()
    plt.figure(figsize=(12,4))
    plt.bar(df_plot.index, df_plot['Volume'], width=1.0)
    plt.yscale("log")
    plt.xticks(rotation=45, ha='right')
    plt.title(f"Volume for {ticker}")
    plt.xlabel("Date")
    plt.ylabel("Volume (log scale)")
    plt.grid(axis='y', linestyle='--', alpha=0.5)
    plt.tight_layout()
    plt.savefig(f"{img_dir}/{ticker}_volume.png", dpi=300)
    plt.close()

    print(f"✅ Saved charts to {img_dir}/")
    # Save signals to CSV
    signals_dir = "signals_csv"
    os.makedirs(signals_dir, exist_ok=True)
    df.to_csv(f"{signals_dir}/{ticker}_signals.csv", index=False)


# Run for multiple tickers
for t in ["DFLI", "BYND", "PCSA", "AAPL", "BITF", "CIGL", "NVDA", "SES"]:
    analyze_ticker(t)
