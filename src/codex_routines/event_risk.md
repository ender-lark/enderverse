# Event Risk Intake Routine

Purpose: normalize supplied daily or weekly event-risk rows into
`src/event_risks.json` so sudden market-moving events cannot stay buried in
unstructured prose.

## Boundaries

- Inputs must be supplied JSON rows from the user, a prior Claude/System update,
  or an explicit market-event scan.
- This routine does not scrape headlines, invent macro narratives, or create
  buy/sell orders.
- Missing input means Event Risk is not checked. It does not mean no event risk.

## Commands

Ingest supplied file rows:

```powershell
python src/event_risk_intake.py <event-risk-json> --out src/event_risks.json --summary src/event_risk_intake_summary.json --merge-existing
```

Ingest supplied stdin JSON:

```powershell
python src/event_risk_intake.py --stdin-json --out src/event_risks.json --summary src/event_risk_intake_summary.json --merge-existing
```

Append one supplied sudden-event headline without shaping JSON first:

```powershell
python src/event_risk_intake.py --title "Iran/oil headline risk can change new-buy timing" --channels "oil,rates,volatility" --tickers "XOP,TNX" --why "Review exposure before adding risk." --trigger "WTI spike or Strait headlines accelerate." --out src/event_risks.json --summary src/event_risk_intake_summary.json --merge-existing
```

Append one supplied headline and immediately refresh the live dashboard:

```powershell
python src/sudden_event_refresh.py --title "Iran/oil headline risk can change new-buy timing" --channels "oil,rates,volatility" --tickers "XOP,TNX" --why "Review exposure before adding risk." --trigger "WTI spike or Strait headlines accelerate."
```

Validate the cache:

```powershell
python src/event_risk_intake.py --validate src/event_risks.json
```

## Surfacing Rules

- High and critical rows promote to conservative Today's Actions review prompts.
- Promoted rows are exposure, hedge, sizing, and wait/act reviews only.
- Medium and low rows stay in `feed.event_risk` and lane status context.
- Missing `src/event_risks.json` leaves the Event Risk lane not checked.
- An empty validated list means checked clear for that supplied scan.
