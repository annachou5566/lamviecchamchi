# Hyperliquid ASXN History execution

Public execution-only repository for the owner-approved Wave Alpha **Hyperliquid ASXN Liquidation History** collector.

## Narrow role

This repository may contain only public-safe code needed to:

1. open an ephemeral Chromium session against `https://hyperscreener.asxn.xyz/`;
2. fetch ASXN aggregate liquidation History from the browser-authenticated page context;
3. strictly normalize bounded daily/hourly aggregates;
4. obtain a short-lived GitHub Actions OIDC token;
5. deliver the minimal normalized Hyperliquid History batch to the protected Wave Alpha ingest route.

It is **not** a Wave Alpha source mirror, database, archive, queue, aggregation owner, frontend owner, general QA runner, or scheduler owner. `annachou5566/test-wa` remains the public QA/qualification repo. Cloudflare remains the recurring Production scheduler owner.

## Hard safety rules

- Public standard GitHub-hosted runner only.
- Workflow is `workflow_dispatch` only. No native GitHub `schedule`, `push`, or `pull_request_target` trigger.
- The collection job is inert unless repository variable `HL_HISTORY_EXECUTION_ENABLED` is explicitly set to `true` in a separately approved later operation.
- No repository-scoped long-lived ingest secret. OIDC is the primary identity path.
- No private Wave Alpha source or proprietary owner-history rows.
- No browser profile/cookie/cache/raw provider-response persistence.
- No market-data artifacts and no Long/Short/Total values in routine logs.
- Missing/403/malformed data fails closed; it is never converted to zero.
- Current revision window is 7 days while provider finality remains unqualified.
- Canonical owner history through `2026-08-24` is outside this repository and must never be rewritten here.
- Hyperliquid realtime remains outside this repository and remains PAUSED/EXCLUDED.

## Workflow activation boundary

Source presence is not runtime authorization. Phase 0C initializes/protects the public execution source only. Production variables/secrets, workflow execution, Cloudflare deployment, database/schema creation, seed/backfill, ingest/read/Cron activation and Hyperliquid realtime activation remain separate Wave Alpha gates.

The workflow name and path are intentionally stable for OIDC policy:

```text
workflow:     Hyperliquid ASXN History collector
workflow_ref: annachou5566/lamviecchamchi/.github/workflows/hyperliquid-asxn-history-collector.yml@refs/heads/main
```
