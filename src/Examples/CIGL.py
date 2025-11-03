import yfinance as yf
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

ticker = "CIGL"  # use a ticker that still trades
df = yf.download(ticker, period="6mo", interval="1d")

print(df.head())  #  this prints first few rows so we see if data loaded

if df.empty:
    print(" No data returned. Try a different ticker.")
    quit()

# Volume z-score
df['vol_z'] = (df['Volume'] - df['Volume'].rolling(20).mean()) / (df['Volume'].rolling(20).std() + 1e-9)

# Price % change
df['return'] = df['Close'].pct_change()

# Rule: pump flag
df['flag'] = (df['vol_z'] > 3) & (df['return'] > 0.1)

# Plot
# Plot price
# --- PRICE CHART ---
plt.figure(figsize=(12,6))
plt.plot(df.index, df['Close'], label="Close Price")
plt.plot(df.index, df['Close'].rolling(20).mean(), label="20-day MA", linestyle='--')

# Mark pump signals
flags = df[df['flag']]
for i, row in flags.iterrows():
    plt.scatter(i, row['Close'], marker='o', color='red')
    plt.text(i, row['Close'], "🚨", fontsize=8)

plt.title(f"Pump-like Signals for {ticker}")
plt.legend()
plt.tight_layout()

plt.savefig(f"images/{ticker}_pump_signal.png", dpi=300)
plt.show()


# --- VOLUME CHART ---
plt.figure(figsize=(12,3))
plt.bar(df.index, df['Volume'])
plt.title(f"Volume for {ticker}")
plt.xlabel("Date")
plt.ylabel("Volume")

plt.tight_layout()
plt.savefig(f"images/{ticker}_volume.png", dpi=300)
plt.show()
