import asyncio
import aiohttp
import pandas as pd
import numpy as np
import logging
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import MinMaxScaler
from datetime import datetime
import os

# ------------------ Config ------------------
COVALENT_API_KEY = ""
CHAIN_ID = "1"  # Ethereum Mainnet
INPUT_FILE = "wallets.csv"
OUTPUT_FILE = "wallet_scores.csv"
CONCURRENCY_LIMIT = 5
RETRY_ATTEMPTS = 3
RETRY_DELAY = 5

# ------------------ Logging ------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# ------------------ Fetching Function ------------------
SEMAPHORE = asyncio.Semaphore(CONCURRENCY_LIMIT)

async def fetch_wallet_transactions(session, wallet):
    url = f"https://api.covalenthq.com/v1/{CHAIN_ID}/address/{wallet}/transactions_v2/?key={COVALENT_API_KEY}"
    for attempt in range(RETRY_ATTEMPTS):
        async with SEMAPHORE:
            try:
                async with session.get(url) as resp:
                    if resp.status == 429:
                        logging.warning(f"[Rate Limited] {wallet} | Retrying in {RETRY_DELAY}s...")
                        await asyncio.sleep(RETRY_DELAY)
                        continue
                    if resp.status != 200:
                        raise Exception(f"{resp.status}, {await resp.text()}")
                    result = await resp.json()
                    txs = result.get("data", {}).get("items", [])
                    df = pd.DataFrame(txs)
                    if not df.empty:
                        df['wallet'] = wallet
                        df['timestamp'] = pd.to_datetime(
                            df['block_signed_at'], format='%Y-%m-%dT%H:%M:%SZ', errors='coerce'
                        )
                    logging.info(f"[Fetched] {wallet} | {len(df)} txs")
                    return df
            except Exception as e:
                logging.warning(f"[Attempt {attempt+1}/{RETRY_ATTEMPTS}] Failed for {wallet}: {e}")
                await asyncio.sleep(RETRY_DELAY)
    return pd.DataFrame()

async def fetch_all(wallets):
    async with aiohttp.ClientSession() as session:
        tasks = [fetch_wallet_transactions(session, w) for w in wallets]
        dfs = await asyncio.gather(*tasks)
    return pd.concat(dfs, ignore_index=True)

# ------------------ Feature Extraction ------------------
def extract_features(df):
    df = df.copy()
    if df.empty:
        return {}

    supply_tx = df[df['value'].astype(str).astype(float) > 0]
    withdraw_tx = df[df['value'].astype(str).astype(float) < 0]

    features = {
        "supply_sum": supply_tx['value'].astype(float).sum(),
        "borrow_sum": withdraw_tx['value'].astype(float).abs().sum(),
        "num_actions": len(df),
        "active_days": (df['timestamp'].max() - df['timestamp'].min()).days + 1,
    }
    features["repay_to_borrow_ratio"] = 0.5  # placeholder
    features["liquidation_rate"] = 0.1       # placeholder
    features["redemption_to_supply_ratio"] = 0.2  # placeholder
    return features

# ------------------ Scoring ------------------
def score_wallets(wallets):
    logging.info("[Step] Fetching transactions...")
    df_all = asyncio.run(fetch_all(wallets))
    logging.info("[Step] Extracting features...")
    grouped = df_all.groupby("wallet")
    feature_rows = []
    for wallet, df in grouped:
        features = extract_features(df)
        features["wallet"] = wallet
        feature_rows.append(features)

    df = pd.DataFrame(feature_rows).set_index("wallet")
    selected = [
        "supply_sum", "borrow_sum", "repay_to_borrow_ratio", "liquidation_rate",
        "redemption_to_supply_ratio", "num_actions", "active_days"
    ]
    X = df[selected].replace([np.inf, -np.inf], np.nan)
    imputer = SimpleImputer(strategy="constant", fill_value=0)
    X_imputed = imputer.fit_transform(X)
    scaler = MinMaxScaler()
    X_scaled = scaler.fit_transform(X_imputed)
    weights = np.array([0.4, -0.3, 0.4, -0.5, 0.3, 0.2, 0.2])
    raw_scores = X_scaled.dot(weights)
    min_score, max_score = raw_scores.min(), raw_scores.max()
    scores = 1000 * (raw_scores - min_score) / (max_score - min_score + 1e-9)
    df["score"] = scores.astype(int)
    df.reset_index(inplace=True)
    return df[["wallet", "score"]]

# ------------------ Main ------------------
if __name__ == "__main__":
    if not os.path.exists(INPUT_FILE):
        logging.error(f"Input file {INPUT_FILE} not found!")
        exit(1)

    wallet_df = pd.read_csv(INPUT_FILE)
    if 'wallet_id' not in wallet_df.columns:
        logging.error("Input CSV must contain a 'wallet_id' column.")
        exit(1)

    wallets = wallet_df['wallet_id'].dropna().unique().tolist()
    df_scores = score_wallets(wallets)
    df_scores.to_csv(OUTPUT_FILE, index=False, encoding='utf-8')
    print("\nDone! Saved scores to:", OUTPUT_FILE)

