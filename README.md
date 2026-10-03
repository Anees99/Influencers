# Starfish Campaign Ops

Automated reconciliation and analytics platform for influencer marketing campaigns. Ingests contracts, invoices, payouts, deliverables, and analytics data to detect financial discrepancies, missing content, and performance anomalies.

## Features

- **Multi-format Ingestion**: Parses PDF (contracts/invoices), XLSX (analytics/payouts), CSV (deliverables), and PNG (screenshots).
- **Creator Matching**: Normalizes creator names with fuzzy matching to link records across files.
- **Reconciliation Engine**: Detects 12+ exception types including payment variances, missing deliverables, duplicate invoices, and late submissions.
- **Analytics Aggregation**: Computes campaign totals (views, reach, engagements, ER%) from raw analytics exports.
- **Stable Exception IDs**: Uses deterministic SHA-1 hashing for exception tracking across re-runs.
- **Export Capabilities**: Generates Excel summaries, narrative reports, and PDF client deliverables.

## Installation

1. Clone the repository:
   ```bash
   git clone <repo-url>
   cd starfish_campaign_ops
