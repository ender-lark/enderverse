# UW Endpoint Matrix For Daily Moves - 2026-07-01

Purpose: keep Unusual Whales usage tied to the operator goal. Endpoints are evidence inputs for a daily decision packet, not raw data decorations.

## Core Daily Opportunity Inputs

| Endpoint/tool | Use | Evidence weight | Follow-up |
| --- | --- | --- | --- |
| Stock screener | IV rank, implied move, IV30, net premium, call/put volume, open interest changes, liquidity, earnings context | Medium | Use to decide whether options are cheap/rich and whether a ticker deserves chain pull |
| Option chains | Contract strikes, expiry, IV, bid/ask, Greeks, volume/OI, defined-risk structure feasibility | High for instrument selection | Required before an options ACT row can be shown |
| Option-contract screener / hottest chains | Unusual contract activity, volume/OI, DTE/delta filters, sweeps/floor/multileg tags when available | Medium | Timing/corroboration only; never standalone thesis proof |
| Option trades | Repeated directional prints near candidate strikes/expiries | Medium | Confirm that flow aligns with the proposed expression |
| Flow alerts | Curated flow anomalies | Low-to-medium | Tie-breaker for timing; require price/thesis confirmation |
| Lit flow | Equity tape accumulation/distribution | Medium | Confirms whether stock flow supports options flow |
| Dark pool | Block/venue context and possible institutional accumulation/distribution | Medium | Useful for sizing/timing caution, not a direct buy trigger |
| Greek/GEX exposure | Pin/squeeze/resistance/support pressure by ticker, expiry, strike | Medium when available | Use for entry timing and event-risk context |
| Correlations | Cluster and factor overlap | Risk-control input | Prevent correlated echoes from being counted as independent confirmation |

## Trump/Social And Political Inputs

| Endpoint/tool | Use | Evidence weight | Follow-up |
| --- | --- | --- | --- |
| News headlines with Truth Social / Trump metadata | Direct Trump/social market-moving post detection when metadata is available | High for source detection, low until ticker impact is confirmed | Normalize to Social Watch with source lineage, then require UW/price/news/Fundstrat/catalyst confirmation before promotion |
| Reddit/social snapshots | Crowd amplification and early anomaly detection, including r/TrumpsTrades | Low | Watch-only; use as a lead to vet, not a trade signal |
| Congress/politician trades | Policy/regulatory corroboration or low-frequency theme support | Low-to-medium | Helpful for research priority, not daily timing alone |
| Insider trades | Slow-moving corroboration | Low-to-medium | Useful for thesis support/conflict, not same-day options timing alone |

## Optional Or Domain-Specific Inputs

| Endpoint/tool | Use | Evidence weight | Follow-up |
| --- | --- | --- | --- |
| Prediction markets | Macro/political event probability context | Low | Context only unless tied to event-risk/portfolio exposure |
| Crypto whale transactions | Crypto-specific risk/opportunity context | Low-to-medium for crypto complex | Use only for BTC/ETH/BMNR/MSTR/crypto-linked lanes |
| Websocket/Advanced-only feeds | Faster live flow, news, and contract-screener channels | Capability dependent | Do not assume production access until proven by endpoint proof |

## Promotion Rules

- One UW endpoint cannot create an ACT recommendation.
- Options ACT requires thesis/conviction context plus usable chain/liquidity/IV/risk data.
- Flow can increase urgency only after it aligns with thesis, price/tape, and risk gates.
- Trump/social rows stay watch-only unless independent non-social evidence confirms material ticker impact.
- Missing endpoint proof stays not_checked; failed or tier-gated endpoints must not read as neutral evidence.
