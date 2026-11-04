"""Apply vendor rules to a bank statement CSV and list what a person must review.

Each rule in the rules file says: if the description contains this text and
the money goes this direction, use this account. Rules marked Review = yes
still need a person every time (tax payments, loans, mixed merchants). Lines
no rule matches are left for a person too. Nothing is guessed.

The output CSV adds Account, Type, Needs review and Reason columns, and the
summary splits money out into what lands on the profit and loss and what
doesn't (transfers, owner's draws, loan payments), so you can see how much
an Uncategorized pile would overstate expenses.

Usage:
  python3 apply_rules.py sample-statement-2026-09.csv vendor-rules.csv --out categorized.csv
Python 3, standard library only. MIT licensed.
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from decimal import Decimal

PL_TYPES = {"Expense", "Cost of goods sold", "Income"}
ALWAYS_ASK = ("ATM", "CASH WITHDRAWAL", "ZELLE TO", "VENMO", "CHECK ")


def load_rules(path: str) -> list[dict]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        rules = list(csv.DictReader(f))
    for r in rules:
        r["Match"] = r["Match"].strip().upper()
        r["Direction"] = (r.get("Direction") or "any").strip().lower()
        r["Review"] = (r.get("Review") or "no").strip().lower()
    return rules


def find_rule(description: str, amount: Decimal, rules: list[dict]) -> dict | None:
    text = description.upper()
    direction = "in" if amount > 0 else "out"
    for rule in rules:
        if rule["Match"] and rule["Match"] in text and rule["Direction"] in ("any", direction):
            return rule
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("statement")
    parser.add_argument("rules")
    parser.add_argument("--out", default="categorized.csv")
    args = parser.parse_args()

    rules = load_rules(args.rules)
    with open(args.statement, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fields = list(reader.fieldnames or [])
        lines = list(reader)
    if "Amount" not in fields or "Description" not in fields:
        sys.exit("The statement CSV needs Description and Amount columns (money out negative).")

    out_fields = fields + ["Account", "Type", "Needs review", "Reason"]
    by_type: dict[str, Decimal] = defaultdict(Decimal)
    review = []
    for line in lines:
        amount = Decimal(line["Amount"].replace(",", ""))
        rule = find_rule(line["Description"], amount, rules)
        if rule:
            line["Account"], line["Type"] = rule["Account"], rule["Type"]
            if rule["Review"] == "yes":
                line["Needs review"], line["Reason"] = "yes", rule.get("Note") or "Rule says check each time"
            else:
                line["Needs review"], line["Reason"] = "no", ""
        else:
            line["Account"], line["Type"] = "Uncategorized", "Uncategorized"
            reason = "No rule matches"
            if amount > 0:
                reason = "Deposit: match it to an invoice, sale or payout before calling it income"
            elif any(word in line["Description"].upper() for word in ALWAYS_ASK):
                reason = "Cash, person-to-person or check: ask the owner what it was for"
            line["Needs review"], line["Reason"] = "yes", reason
        if amount < 0:
            by_type[line["Type"]] += -amount
        if line["Needs review"] == "yes":
            review.append(line)

    with open(args.out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=out_fields)
        writer.writeheader()
        writer.writerows(lines)

    total_out = sum(by_type.values(), Decimal("0"))
    on_pl = sum((v for k, v in by_type.items() if k in PL_TYPES), Decimal("0"))
    print(f"{len(lines)} lines. {len(lines) - len(review)} categorized by rule, {len(review)} need a person.")
    print(f"Wrote {args.out}")
    print()
    print("Money out by type:")
    for kind, value in sorted(by_type.items(), key=lambda kv: -kv[1]):
        print(f"  {kind:<20} {value:>12,.2f}")
    print(f"  {'Total':<20} {total_out:>12,.2f}")
    print(f"Of that, {on_pl:,.2f} is on the profit and loss so far. "
          f"{total_out - on_pl:,.2f} is transfers, draws, loans or still waiting for a person.")
    print()
    print("For a person to review:")
    for line in review:
        print(f"  {line.get('Date', ''):<11} {line['Description']:<32} {line['Amount']:>10}  {line['Reason']}")


if __name__ == "__main__":
    main()
