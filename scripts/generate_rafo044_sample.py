#!/usr/bin/env python
"""Gera amostra Rafo044 (formato compatível) em poucos minutos — POC local/AWS."""

from __future__ import annotations

import argparse
import os
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

UFS_BRANCH = [
    ("BR001", "Melbourne Branch 1", "Melbourne"),
    ("BR002", "Sydney Branch 1", "Sydney"),
]
SEGMENTS = ["retail", "corporate", "premium"]
SEG_PROBS = [0.6, 0.3, 0.1]
TX_TYPES = ["deposit", "withdrawal", "transfer", "payment"]
TX_PROBS = [0.3, 0.3, 0.2, 0.2]


def main() -> None:
    parser = argparse.ArgumentParser(description="Gera data/rafo044/raw para ETL")
    parser.add_argument("--output-dir", default="data/rafo044/raw")
    parser.add_argument("--customers", type=int, default=2000)
    parser.add_argument("--year", type=int, default=2015)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    rng = np.random.default_rng(args.seed)
    out = os.path.abspath(args.output_dir)
    os.makedirs(out, exist_ok=True)

    start = datetime(args.year, 1, 1)
    end = datetime(args.year + 1, 1, 1)

    branches = pd.DataFrame(
        [
            {
                "branch_code": code,
                "branch_name": name,
                "city": city,
                "region": city,
                "manager_id": f"MGR{code}",
                "open_date": "2010-01-01",
                "branch_status": "active",
                "latitude": -37.81,
                "longitude": 144.96,
            }
            for code, name, city in UFS_BRANCH
        ]
    )

    customers = []
    accounts = []
    loans = []
    transactions = []
    tx_id = 1

    for i in range(1, args.customers + 1):
        cid = f"CUST{i:06d}"
        segment = str(rng.choice(SEGMENTS, p=SEG_PROBS))
        gender = str(rng.choice(["M", "F"]))
        age = int(rng.integers(25, 65))
        dob = (datetime.now() - timedelta(days=365 * age)).strftime("%Y-%m-%d")
        branch = UFS_BRANCH[i % len(UFS_BRANCH)][0]
        open_date = start + timedelta(days=int(rng.integers(0, 120)))

        customers.append({
            "customer_id": cid,
            "first_name": f"User{i}",
            "last_name": "Sample",
            "dob": dob,
            "gender": gender,
            "national_id": f"ID{i:08d}",
            "email": f"u{i}@example.com",
            "phone_number": "000",
            "kyc_status": "verified",
            "account_open_date": open_date.strftime("%Y-%m-%d"),
            "customer_segment": segment,
            "branch_code": branch,
        })

        n_acc = 2 if segment == "corporate" else 1
        for a in range(n_acc):
            aid = f"ACC{i:06d}{a}"
            balance = float(rng.uniform(2000, 25000))
            accounts.append({
                "account_id": aid,
                "customer_id": cid,
                "account_type": str(rng.choice(["savings", "current", "credit"])),
                "currency": "AUD",
                "balance": round(balance, 2),
                "branch_code": branch,
                "account_status": "active",
                "created_at": open_date.strftime("%Y-%m-%d"),
                "closed_at": None,
            })

            n_tx = int(rng.integers(24, 48))
            for _ in range(n_tx):
                tx_date = start + timedelta(days=int(rng.integers(0, 364)))
                tx_type = str(rng.choice(TX_TYPES, p=TX_PROBS))
                amount = round(float(rng.lognormal(6.0, 0.6)), 2)
                transactions.append({
                    "transaction_id": f"TX{tx_id:08d}",
                    "account_id": aid,
                    "transaction_type": tx_type,
                    "amount": amount,
                    "currency": "AUD",
                    "transaction_date": tx_date.strftime("%Y-%m-%d"),
                    "branch_code": branch,
                    "merchant_category": "retail",
                    "status": "completed",
                })
                tx_id += 1

        if rng.random() < 0.12:
            loans.append({
                "loan_id": f"LN{i:06d}",
                "customer_id": cid,
                "loan_type": "personal",
                "principal_amount": round(float(rng.uniform(5000, 30000)), 2),
                "interest_rate": round(float(rng.uniform(4, 9)), 2),
                "loan_term_months": 24,
                "start_date": start.strftime("%Y-%m-%d"),
                "end_date": end.strftime("%Y-%m-%d"),
                "payment_frequency": "monthly",
                "loan_status": "active",
                "past_due_amount": 0.0,
            })

    pd.DataFrame(customers).to_csv(os.path.join(out, "customers.csv"), index=False)
    pd.DataFrame(accounts).to_csv(os.path.join(out, "accounts.csv"), index=False)
    pd.DataFrame(loans).to_csv(os.path.join(out, "loans.csv"), index=False)
    branches.to_csv(os.path.join(out, "branches.csv"), index=False)
    pd.DataFrame(transactions).to_parquet(os.path.join(out, "transactions.parquet"), index=False)

    print(f"OK: {out}")
    print(f"  customers={len(customers)} transactions={len(transactions)}")


if __name__ == "__main__":
    main()
