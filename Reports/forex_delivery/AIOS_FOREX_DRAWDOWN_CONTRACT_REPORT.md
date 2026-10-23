# Forex Drawdown Contract

The canonical gate is maximum drawdown as a percentage of running peak equity:

`100 * (running_peak_equity - current_equity) / running_peak_equity`

Paper60's R-only drawdown cannot be reliably converted because its canonical artifacts do not bind starting equity and a fixed per-trade equity-risk fraction. Future research must persist the full compounded equity curve inputs. This is a measurement-contract defect; historical evidence remains unchanged.
