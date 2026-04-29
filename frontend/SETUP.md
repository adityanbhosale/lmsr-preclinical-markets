# Nextra scaffold — execution notes

## What's in this scaffold (now)

Substantially more complete than the initial sketch. Total: 25 files. All sections
referenced in the top-level nav now have at least a stub page; three sections
(Architecture, Layer 2, Mechanism) have full content. Both custom MDX widgets
(`ArchitectureDiagram`, `LiveMarketCard`) are built.

```
package.json                             # All deps including nextra@^4
next.config.mjs                          # Nextra wrapper
mdx-components.tsx                       # MDX customization
app/
  layout.tsx                             # Root — Nextra Layout + Web3Providers
  globals.css                            # Tailwind + Nextra coexistence note
  _meta.ts                               # Top-level nav
  page.mdx                               # Overview / landing
  architecture/
    page.mdx                             # ✓ Full content + diagram
    _meta.ts
    regulatory-split/page.mdx            # ✓ SEC vs CFTC framing
    settlement-stack/page.mdx            # ✓ USDC + JPMD argument
  layer-1/
    page.mdx                             # ✓ ERC-3643 SPV overview
    _meta.ts
    erc-3643/page.mdx                    # ✓ T-REX architecture
    milestone-tokens/page.mdx            # ✓ Per-program token rationale
    deployment/page.mdx                  # ✓ Sepolia coordinates + repro
  layer-2/
    page.mdx                             # ✓ LS-LMSR overview + LiveMarketCard
    _meta.ts
    ls-lmsr/page.mdx                     # ✓ Math + CFMM comparison
    abmm/page.mdx                        # ✓ Seeding formula + retreat
    deployment/page.mdx                  # ✓ Base Sepolia coordinates
  cctp/
    page.mdx                             # ✓ Why CCTP over wrapped bridges
    _meta.ts
    outbound/page.mdx                    # ✓ Sepolia → Base sequence
    return/page.mdx                      # ✓ Base → Sepolia sequence
  mechanism/
    page.mdx                             # ✓ Open theoretical question
    _meta.ts
    retreat-function/page.mdx            # ✓ Derivation + AGT mapping
    backtests/page.mdx                   # ✓ Brier scores per program
  markets/
    page.tsx                             # Live testnet UI relocates here
  deployment/
    page.mdx                             # ✓ All addresses, reproducibility
components/docs/
  ContractAddress.tsx                    # ✓ Copy-to-clipboard widget
  ArchitectureDiagram.tsx                # ✓ SVG dual-layer diagram
  LiveMarketCard.tsx                     # ✓ wagmi multi-market widget
lib/
  markets.ts                             # ✓ Multi-market metadata
```

## What's NOT in this scaffold

- `lib/abis/lslmsr.ts` — your existing file, unchanged. `LiveMarketCard.tsx`
  imports it as `from '../../lib/abis/lslmsr'`. Confirm the path matches your repo.
- `lib/contracts.ts` — your existing file, unchanged.
- `lib/wagmi.ts` — your existing file, unchanged.
- `app/providers.tsx` — your existing file, unchanged. Referenced by `app/layout.tsx`
  as `import { Web3Providers } from './providers'`. Make sure your providers file
  exports a component named `Web3Providers` (or rename the import).
- The `components/` directory besides `components/docs/` — your existing trade UI
  components (TradeForm, PositionCard, MarketHeader, Layer1Display) untouched.

## Execution order tomorrow

### 1. Install dependencies (5 min)

From `frontend/`:

```bash
npm install nextra@^4 nextra-theme-docs@^4
```

Or replace your full `package.json` with the one in this scaffold and run
`npm install`.

### 2. Drop in the scaffold files (15 min)

Working from your `frontend/` directory:

```bash
# Backup first
cp -r app app.backup

# Copy scaffold files (replace paths to match where you downloaded the scaffold)
cp -r /path/to/nextra-scaffold/* .

# The scaffold's app/markets/page.tsx is a placeholder — replace its body
# with the contents of your existing app/page.tsx (which becomes the markets page).
# Or move app.backup/page.tsx → app/markets/page.tsx and adjust imports.
```

Verify your existing `app/providers.tsx` exports a component named `Web3Providers`.
If yours is named differently (e.g., `Providers`), either rename it or update the
import in `app/layout.tsx`.

### 3. Smoke test (5 min)

```bash
npm run dev
```

Hit each top-level route in a browser:

- `localhost:3000/` — overview page renders inside Nextra shell
- `localhost:3000/architecture` — architecture page renders, ArchitectureDiagram
  SVG visible
- `localhost:3000/layer-1` — Layer 1 page renders, ContractAddress widgets
  copy-to-clipboard works
- `localhost:3000/layer-2` — Layer 2 page renders, LiveMarketCard widget loads
  (will show "Loading…" or live data depending on wagmi state)
- `localhost:3000/cctp` — CCTP page renders
- `localhost:3000/mechanism` — Mechanism page renders, math equations display
  (Nextra v4 has KaTeX built in; if math doesn't render, run
  `npm install katex` and import `katex/dist/katex.min.css` in `app/layout.tsx`)
- `localhost:3000/deployment` — All addresses page renders
- `localhost:3000/markets` — Your existing trade UI renders (full-bleed, no docs
  sidebar)

### 4. Wallet connect smoke check on /markets

Connect a wallet on Base Sepolia, verify:
- `useAccount()` returns connected state
- `MarketHeader` reads contract data
- `TradeForm` renders the cost preview correctly

If any of these fail, the issue is the provider composition order in
`app/layout.tsx` — `Web3Providers` must be the *outer* wrapper.

### 5. Build check before deploying

```bash
npm run build
```

Three issues likely to surface on first build:

- **Unused-variable warnings in MDX** — non-blocking, ignore
- **Type errors in `LiveMarketCard.tsx`** — most likely if your `lslmsrAbi` export
  shape differs from what's expected. Adjust the import and the `functionName`
  references to match your ABI's actual function names.
- **Missing `lib/abis/lslmsr` module** — confirm the ABI lives at
  `frontend/lib/abis/lslmsr.ts` (or update the import path in `LiveMarketCard.tsx`)

### 6. Deploy

```bash
vercel --prod
```

Same Vercel project, same domain. The build now produces both the docs site and
the trade UI from a single deployment.

## Tailwind / Nextra coexistence

Nextra v4 ships its own theme CSS. Your existing Tailwind utilities continue to
work for the `/markets` route components. They coexist as long as:

- You don't override `--nextra-*` CSS variables in your global Tailwind layer
- You let Nextra's `nextra-theme-docs/style.css` import (in `app/layout.tsx`)
  ship before your `globals.css`

If a Tailwind utility doesn't apply on `/markets`, the cascade order is the
likely cause. Either add `!important` to the utility or scope it under a parent
class.

## What's still left to do

The scaffold gets you to a presentable docs site that's outreach-ready. Three
things are explicitly unfinished:

1. **Three `lib/markets.ts` addresses are `null`** — adagrasib, vepdegestrant,
   BI-1701963. Until those LSLMSR contracts are deployed on Base Sepolia, the
   LiveMarketCard widget shows "Pending deployment" for those three. Deploying
   them is the next contracts-side workstream.

2. **Math rendering** — Nextra v4 has KaTeX integration, but you may need to
   install `katex` and import its CSS in `app/layout.tsx`. Test on the Mechanism
   pages first.

3. **`theme.config.tsx`** — Nextra v4 moved theme config into `app/layout.tsx`
   props (which I've configured), so a separate `theme.config.tsx` file is not
   strictly needed. If you want a logo, custom footer link list, etc., extend the
   `<Layout>` props in `app/layout.tsx`.

## Rough budget

The scaffold drops in cleanly in ~30 min. After that:

- Smoke test + wallet connect verification: 15 min
- Math rendering setup if needed: 15 min
- Deploy and verify production: 10 min
- Iterating on content / catching typos: ongoing

Realistic total to a deployable docs site that's ready for outreach links: **one
focused 90-minute session**.
