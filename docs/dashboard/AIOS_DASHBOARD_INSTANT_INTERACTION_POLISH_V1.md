# AIOS Dashboard Instant Interaction Polish V1

## Scope

This bounded dashboard UI slice improves local interaction and responsive rendering without changing dependencies, data sources, or execution authority. The home surface keeps exactly four rooms in this order: 🔐 Access, 📈 Forex Bot, 🛠️ Utilities, and 🎵 Music.

## Interaction contract

- Room changes use immediate local React state only.
- Opening a room moves keyboard focus to its back button.
- Back or Escape returns home and restores focus to the room button that opened the detail view.
- Buttons expose visible keyboard focus, touch-friendly hit areas, and pressed feedback.
- Reduced-motion preferences remove decorative button movement.

## Responsive rendering contract

- Dynamic viewport units and safe-area insets support mobile and foldable viewports.
- Root and dashboard surfaces prevent accidental horizontal overflow.
- Room, status, and pair grids rebalance across narrow and wide screens.
- The Forex lock strip presents all four safety states evenly on wider screens and stacks on narrow screens.
- Pair cards preserve readable flags, pair names, and watch states at compact widths.

## Safety boundary

The slice adds no dependency, network request, polling, timer, analytics, telemetry, broker connection, credential access, or order control. The Forex room remains `READ ONLY`, `DISPLAY_ONLY`, `EXEC OFF`, `BROKER LOCKED`, and `Paper-only`.

## Validation

The required validation chain is dashboard lint, dashboard production build, dashboard pytest suite, `git diff --check`, dependency-file hash comparison, static safety inspection, changed-path inspection, and bundle-size comparison against the pre-change baseline.
