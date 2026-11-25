# Scenarios Page Plan

## Overview

Rename the sidebar entry "CEP Patterns" to "Scenarios" and turn the CEP page into a
multi-scenario page. Scenarios are grouped in two sections:

1. **Transaction generation** (new, moved from the Transactions page)
   - "Create 200 transactions" (existing `POST /transactions/generate` behaviour)
   - "Create transactions for Mr Carter" (new: a batch of ~20 random realistic
     transactions only on James Carter's accounts/cards, reusing the existing generator)
2. **Complex Event Processing** (existing three `MATCH_RECOGNIZE` scenarios: Fraud Probe,
   Merchant Streak, SMB Spike, kept as a sub-part, behaviour unchanged)

Decisions confirmed with the user:
- Carter scenario = random realistic batch (~20), generator filtered to Carter's `customer_id`.
- Route renamed to `/scenarios`; `/cep` redirects to it.
- Run results are displayed inline on the Scenarios page (summary), with a link to the full list.
- "Generate 200 transactions" button is removed from the Transactions page.
- The `/transactions/generated` page is kept and reused: after a generation scenario runs, the
  Scenarios page offers a "View generated transactions" link that navigates to it, passing the
  created transactions via router state (same mechanism as today). Its back link points to
  `/scenarios` instead of `/transactions`.

Non-goals: no change to the CEP scenario registry/runner, no change to Flink/dbt pipelines.

## Sub-Tasks

### 1. Backend: generate transactions for a single customer
- **Intent**: let the existing generator produce a batch restricted to one customer, so the Carter scenario reuses it rather than duplicating logic.
- **Expected Outcomes**: `POST /transactions/generate` with no params behaves exactly as today (200 txns). With `customer_id` and `count` query params it creates `count` transactions only on that customer's active accounts/cards. Unknown customer / no eligible accounts returns the existing 409.
- **Todo List**:
  1. Add optional `customer_id` and `count` parameters to `transactions.service.generate()`; filter `accounts_service.list_all()` to that customer and cards to those accounts before calling `generator.generate(..., count=...)`.
  2. Add optional query params `customer_id: UUID | None` and `count: int | None` (bounded, e.g. 1–500 via validation) to `generate_transactions()` in the resource and pass them through.
  3. Add backend tests: filtered generation only yields Carter's `customer_id`, honours `count`, 409 when customer has no eligible account; existing default tests remain green.
- **Relevant Context**: `apps/backend/transactions/service.py` (`generate`), `apps/backend/transactions/generator.py` (`generate`, `DEFAULT_COUNT`, `NoEligibleAccountsError`), `apps/backend/api/transaction_resource.py` (`generate_transactions`), `apps/backend/tests/test_transactions_generate.py`. Carter customer id `00000000-0000-0000-0000-ef1234567890` (`apps/backend/customers/data/customers.csv`, also `_CARTER` in `apps/backend/scenarios/registry.py`).
- **Status**: `[x] done`
- **Outcome / notes for next sub-tasks**:
  - Endpoint: `POST /api/v1/transactions/generate?customer_id=<uuid>&count=<1..500>`. Both query params are optional; no params => unchanged (200 txns, all customers). Response is still `201` with `Transaction[]`.
  - Validation: `count` outside 1-500 or non-integer, or malformed `customer_id`, returns `422`. Unknown customer or no eligible (ACTIVE, open) account returns `409` with `detail: "No active accounts available"`.
  - Python: `transactions.service.generate(customer_id: UUID | None = None, count: int | None = None)`. Cards are filtered to the customer's accounts.
  - Tests added/updated in `apps/backend/tests/test_transactions_generate.py`; full suite: `uv run pytest` => 268 passed, 27 skipped.
  - Frontend: Carter requests should use `customer_id=00000000-0000-0000-0000-ef1234567890&count=20`; the frontend must handle the 409 case (show error message).

### 2. Frontend API client update
- **Intent**: expose the new parameters to the UI.
- **Expected Outcomes**: `generateTransactions()` accepts optional `{ customerId, count }` and builds the query string; default call is unchanged.
- **Todo List**:
  1. Update `generateTransactions` in `apps/frontend/src/api/transactions.ts`.
  2. Define the Carter customer id constant in the Scenarios page (or a small shared constant), not hardcoded in the API client.
- **Relevant Context**: `apps/frontend/src/api/transactions.ts`, `apps/frontend/src/api/client.ts` (`request<T>`).
- **Status**: `[x] done`
- **Outcome / notes for next sub-tasks**:
  - `generateTransactions(options?: GenerateTransactionsOptions): Promise<Transaction[]>` exported in `apps/frontend/src/api/transactions.ts`.
  - `GenerateTransactionsOptions`: `{ customerId?: string; count?: number }`.
  - When options are omitted/empty, sends `POST /transactions/generate` unchanged.
  - When params are present, formats as query parameters (`/transactions/generate?customer_id=...&count=...`).
  - Unit tests in `apps/frontend/src/api/transactions.test.ts` verify default call and query string serialization. All frontend unit tests, typecheck (`tsc -b`), and linter pass cleanly.

### 3. Scenarios page (rename + restructure CEP page)
- **Intent**: single page with the generation scenarios on top and the CEP scenarios as a sub-section.
- **Expected Outcomes**: Page titled "Scenarios". Section "Transaction generation" with two scenario cards (200 transactions, Carter transactions), each with a run button, spinner/disabled state, error message, and an inline results table of the created transactions. Section "Complex Event Processing" contains the unchanged three pattern cards and detail panel.
- **Todo List**:
  1. Rename `CEPPage.tsx` → `ScenariosPage.tsx` (and its test file); keep CEP logic intact as a sub-section.
  2. Add the generation scenarios, reusing existing CSS classes (`cep-card`, `cep-detail`, `table`, `btn`, `status-msg`); add a minimal section-heading style only if needed in `src/styles/index.css`.
  3. Inline results table for generated transactions (type, amount, merchant, category, time) plus a "View generated transactions" link/button that does `navigate('/transactions/generated', { state: { transactions } })`. For 200 rows, the inline table may be limited to a short summary (count + first rows) since the full list is on the generated page.
  4. Update page subtitle text to describe scenarios rather than only CEP.
- **Relevant Context**: `apps/frontend/src/pages/CEPPage.tsx`, `apps/frontend/src/pages/CEPPage.test.tsx`, `apps/frontend/src/styles/index.css` (cep-* classes ~380-425), `apps/frontend/src/types/transaction.ts`, `apps/frontend/src/types/scenario.ts`.
- **Status**: `[x] done`
- **Outcome / notes for next sub-tasks**:
  - Renamed (via `git mv`) `CEPPage.tsx` → `ScenariosPage.tsx` (default export `ScenariosPage`) and `CEPPage.test.tsx` → `ScenariosPage.test.tsx`. CEP logic is untouched (cards, detail panel, trigger/result).
  - Page title is now "Scenarios" (h1) with subtitle; h2 "Transaction generation" (two `GenerationScenario` cards: "Create 200 transactions" → `generateTransactions(undefined)`, "Create transactions for Mr Carter" → `generateTransactions({ customerId: '00000000-0000-0000-0000-ef1234567890', count: 20 })`) and h2 "Complex Event Processing".
  - Each generation card: running/disabled button ("Generating…"), error message (`ApiError.message`, e.g. 409 "No active accounts available"; otherwise "Failed to generate transactions"), inline summary ("N transactions written" + first 5 rows preview) and a "View generated transactions" button → `navigate('/transactions/generated', { state: { transactions } })`.
  - CSS: added only `.scenarios-section__title`, `.scenarios-section__intro`, `.scenario-card` at the end of `src/styles/index.css`.
  - **App.tsx (minimal)**: only the import and the element were renamed; the route path is STILL `/cep` (`<Route path="/cep" element={<ScenariosPage />} />`, line ~38). Sub-Task 4 must change it to `/scenarios`, add `<Navigate to="/scenarios" replace />` for `/cep`, update `Sidebar.tsx` (and `Sidebar.test.tsx`, which exists) and the `GeneratedTransactionsPage` back links/tests.
  - `TransactionsPage.tsx`/`.test.tsx` are untouched: the "Generate 200 transactions" button and its tests still exist there (Sub-Task 5 removes them; the navigation test equivalent already lives in `ScenariosPage.test.tsx`).
  - Validation (`apps/frontend`): `npm test` 24 files / 121 tests pass; `npm run build` (`tsc -b && vite build`) OK; `npm run lint` 0 errors, 7 pre-existing warnings in other pages (none in ScenariosPage).

### 4. Navigation and routing
- **Intent**: rename the nav entry and route.
- **Expected Outcomes**: Sidebar shows "Scenarios" linking to `/scenarios`; `/cep` redirects to `/scenarios`; the `/transactions/generated` route remains and its back link returns to the Scenarios page.
- **Todo List**:
  1. `Sidebar.tsx`: `{ to: '/scenarios', label: 'Scenarios', Icon: Zap }`.
  2. `App.tsx`: route `/scenarios` → `ScenariosPage`; add `<Navigate to="/scenarios" replace />` for `/cep`; keep the `/transactions/generated` route.
  3. `GeneratedTransactionsPage.tsx`: change both "Back to transactions" links to "Back to scenarios" → `/scenarios`; update `GeneratedTransactionsPage.test.tsx` accordingly.
- **Relevant Context**: `apps/frontend/src/components/Sidebar.tsx:25`, `apps/frontend/src/App.tsx:12,33,38`.
- **Status**: `[x] done`
- **Outcome / notes for next sub-tasks**:
  - `Sidebar.tsx`: entry is now `{ to: '/scenarios', label: 'Scenarios', Icon: Zap }`. `Sidebar.test.tsx` gained a test (Scenarios link → `/scenarios`, no "CEP Patterns" link).
  - `App.tsx`: `/scenarios` → `ScenariosPage`; `/cep` → `<Navigate to="/scenarios" replace />`; `/transactions/generated` route unchanged. New `src/App.test.tsx` (mocks `AppLayout` and `ScenariosPage`) covers `/scenarios` and the `/cep` redirect.
  - `GeneratedTransactionsPage.tsx`: both links are now "Back to scenarios" → `/scenarios`; its test updated (empty-state and populated-state assertions).
  - Only comment updated elsewhere: `src/styles/index.css` heading comment ("Scenarios page: CEP patterns"). Grep of `apps/frontend` shows no remaining `/cep` (other than the redirect) or "CEP Patterns" references (other than the negative Sidebar assertion).
  - Not yet touched (Sub-Task 5): `TransactionsPage.tsx`/`.test.tsx` still contain the "Generate 200 transactions" button, `handleGenerate`, state and tests. Docs (`docs/demo_script.md`, README) still mention old names (Sub-Task 6).
  - Validation (`apps/frontend`): `npm test` 25 files / 124 tests pass; `npm run build` OK (only the pre-existing chunk-size warning); `npm run lint` 0 errors, 7 pre-existing warnings.

### 5. Remove the button from the Transactions page
- **Intent**: generation now lives on the Scenarios page.
- **Expected Outcomes**: No "Generate 200 transactions" button, handler, state, or error display on the Transactions page; its tests updated.
- **Todo List**:
  1. Remove button, `handleGenerate`, `generating`/`generateError` state and unused imports (`useNavigate`, `generateTransactions`) in `TransactionsPage.tsx`.
  2. Remove the generate-related tests in `TransactionsPage.test.tsx` (lines ~85-122 region, including the `/transactions/generated` StateProbe route); equivalent navigation test moves to the Scenarios page test.
- **Relevant Context**: `apps/frontend/src/pages/TransactionsPage.tsx:23-33,61-63`, `apps/frontend/src/pages/TransactionsPage.test.tsx`.
- **Status**: `[x] done`
- **Outcome / notes for next sub-tasks**:
  - `TransactionsPage.tsx`: removed the "Generate 200 transactions" button, `handleGenerate`, `generating`/`generateError` state, the generate error display and the `generateTransactions` import. `useNavigate` is kept (still used by the row "View" button); `ApiError` also still used by the load error. Header now only has the "Add transaction" link.
  - `TransactionsPage.test.tsx`: removed the `generate button` describe block (incl. the `/transactions/generated` StateProbe route) and the now-unused imports (`userEvent`, `waitFor`, `Route`, `Routes`, `useLocation`). The 4 list/render tests remain. Navigation test equivalent lives in `ScenariosPage.test.tsx`.
  - Validation (`apps/frontend`): `npm test` 25 files / 122 tests pass; `npm run build` OK (only the pre-existing chunk-size warning); `npm run lint` 0 errors, 7 pre-existing warnings.
  - ScenariosPage section borders untouched.

### 6. Docs and validation
- **Intent**: keep docs consistent and verify everything passes.
- **Expected Outcomes**: Demo script refers to "Scenarios" page; tests, typecheck, lint pass.
- **Todo List**:
  1. Update `docs/demo_script.md` (~lines 330-344) for the new page name and describe the two generation scenarios; grep for other "CEP Patterns" / "Generate 200" references.
  2. Run backend tests (`cd apps/backend && uv run pytest`) and frontend tests, typecheck/lint/build (`cd apps/frontend`, npm scripts from `package.json`).
- **Relevant Context**: `docs/demo_script.md`, `apps/frontend/package.json`, `apps/backend/pyproject.toml`.
- **Status**: `[x] done`
- **Outcome / notes**:
  - `docs/demo_script.md`: Transactions section now points to the "Create 200 transactions" scenario on the Scenarios page (and notes the Transactions page has no generate button). The former "Complex Event Processing" `###` section became `### Scenarios` (sidebar entry, `/scenarios` route, `/cep` redirect) with `#### Transaction generation` (Create 200 transactions; Create transactions for Mr Carter = 20 random transactions on James Carter's accounts) and `#### Complex Event Processing` (Fraud Probe, Merchant Streak, SMB Spike unchanged).
  - Repo grep (excluding node_modules/.venv/.git/site) found no other live references; the historical `.bob/plans/generate-transactions-plan.md` and the generated `site/` HTML were left as is. README only has a changelog line mentioning CEP use cases (kept).
  - Validation: backend `uv run pytest` => 268 passed, 27 skipped; frontend `npm test` => 25 files / 122 tests pass; `npm run build` OK (pre-existing chunk-size warning); `npm run lint` 0 errors, 7 pre-existing warnings.
