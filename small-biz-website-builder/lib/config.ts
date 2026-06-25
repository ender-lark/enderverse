// Central config + mock toggle. Every external adapter checks MOCK_MODE.
export const MOCK_MODE = process.env.MOCK_MODE !== "false"; // default ON (safe / free)
export const ANTHROPIC_MODEL = process.env.ANTHROPIC_MODEL ?? "claude-sonnet-4-6";
export const MONTHLY_SPEND_CAP_USD = Number(process.env.MONTHLY_SPEND_CAP_USD ?? "50");

// Quality filter defaults (Plan 03) — tune here.
export const FILTER = { minRating: 4.3, minReviews: 25 };

// Per-zip cost estimate (cents) for the cost guardrail (Research 05: ~$1/zip relying on Search).
export const EST_COST_PER_ZIP_CENTS = 100;
