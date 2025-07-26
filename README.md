# compound_wallet_risk_scoring
A rule-based risk scoring system for Ethereum wallets interacting with the Compound protocol. It retrieves wallet transaction data using the Covalent API, extracts behavioral and financial features (such as borrow/repay ratios, activity span, liquidation indicators), and assigns a normalized risk score between 0–1000.

# 🧾 Risk Scoring Report

## ✅ 1. Data Collection Method

We used the **Covalent API** to retrieve on-chain transaction data for a list of Ethereum wallet addresses.

- Wallets were read from a `wallets.csv` file.
- For each wallet:
  - Transaction history was fetched using Covalent’s `transactions_v2` endpoint.
  - Responses were parsed to extract relevant fields like `timestamp`, `value`, and method type (e.g., supply, borrow, repay).
- We used asynchronous I/O (`aiohttp`) to parallelize data fetching and handle rate limits gracefully.

---

## ✅ 2. Feature Selection Rationale

We derived behavior-based features relevant to lending/borrowing behavior on protocols like Compound. These features capture a wallet’s financial activity and risk exposure:

| Feature | Description |
|--------|-------------|
| `supply_sum` | Total amount supplied (suggests participation as a lender) |
| `borrow_sum` | Total borrowed value (indicates debt exposure) |
| `repay_to_borrow_ratio` | Ratio of repaid to borrowed amount (proxy for repayment reliability) |
| `liquidation_rate` | Proportion of transactions that resulted in liquidation (higher = riskier) |
| `redemption_to_supply_ratio` | Indicates how quickly funds are withdrawn after supply (may hint at yield farming or unstable behavior) |
| `num_actions` | Total number of supply/borrow/repay actions (more = experienced user) |
| `active_days` | Time duration between the first and last activity (longer = more consistent user) |

Each feature was selected based on its relevance to lending behavior and potential for risk identification.

---

## ✅ 3. Scoring Method

We used a **heuristic rule-based model** to calculate wallet credit scores:

- Normalize all features using **Min-Max scaling** to bring them into the range [0, 1].
- Assign weights based on risk implications:

```text
+0.3 → repay_to_borrow_ratio
+0.2 → supply_sum
+0.2 → redemption_to_supply_ratio
+0.1 → num_actions
+0.1 → active_days
-0.3 → borrow_sum
-0.4 → liquidation_rate
```

- Weighted sum of selected features:

```text
score = X_scaled.dot(weights)
```

- The weights reflect whether a feature reduces risk (+) or increases risk (–).

- Final scores are rescaled to a range of 0 to 1000:

```text
credit_score = 1000 * (score - min_score) / (max_score - min_score)
```

This method ensures interpretability and aligns with known DeFi behaviors.

## ✅ 4. Justification of the Risk Indicators
- **Positive weights (low risk):**

  - repay_to_borrow_ratio: High = reliable borrower.

  - supply_sum, num_actions, active_days: High = more engaged, mature users.

  - redemption_to_supply_ratio: Indicates financial discipline.

- **Negative weights (higher risk):**

  - borrow_sum: Large outstanding debt = higher risk.

  - liquidation_rate: Frequent liquidation suggests poor risk management.
