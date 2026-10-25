# Crossroads

A customer advisor for Toyota Financial Services. A customer facing the end of a lease or loan sees where they stand (**Overview**), what each option would cost over five years and which one fits (**Your paths**), and Toyota staff see what those choices are worth across the portfolio (a separate, signed-in **internal dashboard**).

Every number comes from a deterministic Python engine with tests. The language model only writes the explanation, and every number in its text is checked against the engine before it is shown. All data is synthetic.

## Run it

```bash
cp .env.example .env     # keys are optional; every integration has a fake or fallback
docker compose up --build
docker compose run --rm customer-api python -m crossroads.seed.load
```

- Customer app: http://localhost:8080
- Internal dashboard: http://localhost:8081 (needs `STAFF_USER`, `STAFF_PASSWORD_HASH`, `SESSION_SECRET`; see `.env.example` and the quickstart)

**Using the real services.** Put your `NESSIE_API_KEY`, `SERPAPI_API_KEY`, `GEMINI_API_KEY` and `GEMINI_MODEL` in `.env`, then run the seed again: `docker compose run --rm customer-api python -m crossroads.seed.load`. Customers an earlier offline run made from the in-memory fake are replaced by real ones (created once in your Nessie sandbox, which cannot delete them); a customer who already has real Nessie accounts is never created twice, so re-running is safe. The money panel and market value then say where each figure came from. If a `live` Compose project already holds a real seed, `COMPOSE_PROJECT_NAME=live docker compose up` reuses it without creating anything new.

Tests run offline: `docker compose run --rm customer-api pytest` and `npm test` in each app. Deploying to a Vultr instance is in [quickstart.md](specs/001-crossroads-path-advisor/quickstart.md).

## Demo script (about 3 minutes)

> **Pitch line:** "In production, the customer would sign in and see only their own account."
> The "Demo customer" picker stands in for that sign-in.

1. **Overview.** Pick a customer in the *Demo customer* picker. Point out the contract, the mileage trend with the projected overage, their money, and the car's market value. Switch customers: nothing carries over. Toggle *Payments* for the principal and interest split, and press *Sync from my bank* to re-read that customer's figures from Nessie live.
2. **Your paths.** Open *Your paths*. Each option shows its 5-year cost, monthly payment and upfront cost; one is recommended, with a plain-language explanation and a "Numbers verified" badge. Options the customer cannot afford stay visible with the reason. Every path except the recommended one also says, in one line, why it lost ("Costs $2,310 more over 5 years" or "Needs $1,200 more cash upfront"), worked out by the engine and checked like every other figure.
3. **Sliders and questions.** Move miles per year, budget, years to keep, and rate. Results and the recommendation update at once, and "what would change the answer" lists the single input change that flips it. Then type a question in *Ask about your options*: Gemini writes the answer, but every figure in it is filled in by the engine and checked first, so a question like "what if I pay $500 more?" gets an honest answer, never an invented number.
4. **Next step.** Press the next-step button, then *Talk to a specialist*: a confirmation naming the path and the three nearest Toyota dealers.
5. **When nothing is affordable.** Pick **Patricia Miller** (a lease) or **Linda Wolfe** (a loan). Neither has an affordable option, and the app says so: for example "needs $700 more in the bank to cover a month of bills" and "needs $3,700 more cash upfront" (Linda: $1,200 and $3,408). *When nothing is affordable, we say so and show the shortfall.* The business view counts these two customers separately, not as zero savings.
6. **Business view.** Open the internal dashboard on its own address and sign in as staff. Show retained customers, estimated 5-year revenue, average savings (over the customers who have an affordable option), explanations verified, the path mix, and the value-by-path table. Press *Refresh* to recompute every customer. The totals equal the sum of the individual results.
7. **Separation.** The customer app has no link to the dashboard, and `curl -i localhost:8081/api/internal/portfolio` returns `401`.

8. **Under the hood (Tiger Data).** Show the three hypertables and the compression the seed just applied:
   `docker compose exec db psql -U crossroads -c "select * from hypertable_compression_stats('payments')"`.
   The 12 demo customers are too few rows to compress well (about 1.2x), so run the scale demo, which loads
   a million synthetic hourly readings into a scratch hypertable and drops it afterwards:
   `docker compose run --rm customer-api python scripts/compression_demo.py` (measured: 1,080,000 rows, 75.7 MB to 8.0 MB, 89% saved).
   Synthetic readings are more regular than real telemetry, so real data would compress less.

9. **Fairness check.** On the internal dashboard open *Fairness*. It asks one question: does the app steer lower-income customers toward paths that earn Toyota more interest? It scores a separate seeded synthetic population of 500 customers (not the 12 demos, no Nessie, SerpApi or Gemini) with the same engine, splits them into three income bands, and ranks each customer's recommended path among their own affordable options by Toyota's 5-year interest income. The verdict is one of three fixed sentences (no evidence, possible steering, not enough customers), with the lowest-vs-highest gap, a seeded 95% bootstrap interval and the customer counts behind it. It is shown whichever way it comes out, and the limits (income only, synthetic, not a legal finding) are on the same screen. Loan and lease gaps are shown separately as evidence. The customer app has no link to it.

Customer names are generated by a seeded script, so they are the same on every run.

## Built with, track by track

Figures below were measured on a live run (24 Oct 2026), not estimated.

| Track | What it does here | Measured |
|---|---|---|
| **Toyota: What's your next move?** | One customer, one question: the engine compares every option for their loan or lease over 5 years (cost, payment, upfront), recommends one, says why in plain words, shows what would change the answer, and ends in a next step (self-service, eligible offer, or specialist follow-up). The business view shows retention, revenue and service effort. All data is synthetic. | 12 customers; 83% retained, $54,670 estimated 5-year revenue, 42% of recommendations need no specialist; 2 customers with no affordable option are shown with their shortfall |
| **Toyota: responsible AI** | A fairness check on the staff dashboard: 500 seeded synthetic customers, three income bands, a percentile-bootstrap 95% interval (1,000 resamples, fixed seeds), a verdict that can read "possible steering" (a rigged test population always does) and states its limits. No language model writes any figure or sentence. | Opens in 0.17 s; offline run: the lowest-income band's recommendations rank 34.1 points *lower* in profitability to Toyota than the highest band's (95% interval -41.0 to -27.2), so "no evidence of steering" |
| **Capital One Nessie** | Customers, accounts, bills, deposits and purchases are created in the real Nessie API and read back; balances, income and bills on the Overview come from what Nessie returned, and the screen says so. | 12 customers, 24 accounts, 72 bills, 36 deposits, 288 purchases created and read back, 0 mismatches; "Sync from my bank" re-reads one customer live in about 0.5 s. The live API needed four fixes the docs did not mention (https, a merchant, `status` on deposits and purchases, string merchant category), all now covered by tests |
| **SerpApi** | `google_maps` finds the 3 nearest Toyota dealers for the next step; `google` search results give local used-car prices behind each car's market value, which the screen labels "Google results via SerpApi" or "Demo data". Both are cached in the database and fall back cleanly. | Dealers for 6 of 6 ZIPs; real listing quotes for 7 of 11 cars (the other 4 had too few usable prices and show demo data) |
| **Gemini** | `gemini-3.6-flash` with structured output writes each explanation as text with named placeholders; the engine fills in the numbers and a check confirms every figure matches before anything is shown. If the model is down or a figure fails the check, a checked template is used instead, so the model never supplies a number. | 94 live explanations across all 12 customers and several slider settings, 94 passed the check; median 1.4 s after limiting thinking (9.5 s before); dashboard Refresh recomputes all 12 in about 20 s; the question box answered live questions, including ones with numbers and an instruction-override attempt, without ever showing a figure the engine did not supply |
| **Tiger Data** | Three hypertables (odometer readings, payments, transactions), three real-time continuous aggregates behind the trend charts, and compression policies that compress chunks older than 30 days, segmented by customer. The Overview's Payments view reads the `monthly_payments` aggregate. | Demo data about 1.2x. At scale, 1,080,000 synthetic hourly readings went from 75.7 MB to 8.0 MB (89% saved, 9.5x) |
| **Vultr** | Production overlay: Caddy gets TLS certificates for the customer and staff sites, only ports 80 and 443 are open, the database and both APIs are never published, and the staff cookie is Secure. Steps are in [quickstart.md](specs/001-crossroads-path-advisor/quickstart.md). | Verified locally on the production overlay (HTTPS served, HTTP redirects, staff API 401 without sign-in, only Caddy publishes ports). **Not yet deployed to a Vultr instance**: add the live URLs here once it is |

## Where things are

| | |
|---|---|
| `backend/` | engine, explanations, adapters, both APIs, tests |
| `customer-app/`, `internal-app/` | the two React apps |
| `deploy/`, `docker-compose.prod.yml` | production front door (Caddy, TLS) |
| `specs/001-crossroads-path-advisor/` | spec, plan, tasks, contracts, quickstart |

## Brand

Both apps use one set of brand tokens (colours, fonts, sizes, spacing, radii, chart colours, motion) from `branding/tokens.css`. Edit that file, then run `scripts/sync-tokens.sh` to copy it into both apps (each builds from its own folder in Docker). `backend/tests/api/test_brand_tokens.py` fails if either copy differs or if any stylesheet or component hard-codes a colour, font, size, spacing, radius, shadow or gradient. Put a logo in either header and on the staff sign-in card by setting `CUSTOMER_LOGO_URL` or `INTERNAL_LOGO_URL` in `.env` (an image address, not a secret) and rebuilding; with none set a same-size placeholder is shown.
