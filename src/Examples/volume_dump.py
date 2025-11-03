import yfinance as yf
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import os

ticker = "SES"  # use a ticker that still trades
df = yf.download(ticker, period="6mo", interval="1d")

# Create image directory for this ticker
img_dir = f"images/{ticker}"
os.makedirs(img_dir, exist_ok=True)

# FIX: Reset index to flatten any MultiIndex issues
if isinstance(df.columns, pd.MultiIndex):
    df.columns = df.columns.droplevel(1)

# Debug prints
print("DataFrame shape:", df.shape)
print("Index type:", type(df.index))
print("Columns:", df.columns.tolist())
print("\nFirst few rows:")
print(df.head())
print("\nData types:")
print(df.dtypes)

if df.empty:
    print("No data returned. Try a different ticker.")
    quit()

# Volume z-score
df['vol_z'] = (df['Volume'] - df['Volume'].rolling(20).mean()) / (df['Volume'].rolling(20).std() + 1e-9)

# Price % change
df['return'] = df['Close'].pct_change()

# Rule: pump flag
df['flag'] = (df['vol_z'] > 3) & (df['return'] > 0.1)

# --- PRICE CHART ---
plt.figure(figsize=(12,6))
plt.plot(df.index, df['Close'], label="Close Price")
plt.plot(df.index, df['Close'].rolling(20).mean(), label="20-day MA", linestyle='--')

flags = df[df['flag']]
for i, row in flags.iterrows():
    plt.scatter(i, row['Close'], marker='o', color='red', s=100, zorder=5)
    plt.text(i, row['Close'], "🚨", fontsize=12, ha='center')

plt.title(f"Pump-like Signals for {ticker}")
plt.legend()
plt.xlabel("Date")
plt.ylabel("Price")
plt.tight_layout()

# Save to ticker folder
plt.savefig(f"{img_dir}/{ticker}_pump_signal.png", dpi=300)
plt.show()

# --- VOLUME CHART ---
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

# Save to ticker folder
plt.savefig(f"{img_dir}/{ticker}_volume.png", dpi=300)
plt.show()
