import yfinance as yf
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# -------- Settings --------
ticker = "AAPL"  
df = yf.download(ticker, period="6mo", interval="1d")

print(df.head())  # confirms data loaded

# -------- Validate data --------
if df.empty:
    print("No data returned. Try another ticker.")
    quit()

# -------- Feature Engineering --------
df['vol_z'] = (df['Volume'] - df['Volume'].rolling(20).mean()) / (df['Volume'].rolling(20).std() + 1e-9)
df['return'] = df['Close'].pct_change()
df['flag'] = (df['vol_z'] > 3) & (df['return'] > 0.10)

# -------- PRICE CHART --------
plt.figure(figsize=(12,6))
plt.plot(df.index, df['Close'], label="Close Price")
plt.plot(df.index, df['Close'].rolling(20).mean(), label="20-day MA", linestyle="--")

flags = df[df['flag']]
for date, row in flags.iterrows():
    plt.scatter(date, row['Close'], color='red')
    plt.text(date, row['Close'], "🚨", fontsize=8)

plt.title(f"Pump Signals: {ticker}")
plt.legend()
plt.tight_layout()

plt.savefig(f"images/{ticker}_pump_signal.png", dpi=300)
print("Price chart ready")

# ✅ show but don't block so second chart also opens
plt.show()


