# Forex V2 Research

## Corpus And Split

Corpus `AIOS_FOREX_M5_IMMUTABLE_CORPUS_V1` uses chronological development and provisional-validation segments. The old holdout is consumed and was not used for alternative-family promotion. Drawdown is percentage from running peak equity using fixed 0.25% risk per trade.

## Preserved Supertrend Baseline

Development LONG: `{"average_loss_r":-0.7698104724879612,"average_win_r":0.8307524085253295,"ending_equity":0.00036162968316734786,"exit_reasons":{"OPPOSITE_TRUE_CLOSE":4,"SUPERTREND_STOP":15207,"TAKE_PROFIT":2},"expectancy_r":-0.5100464710929822,"largest_pair_share":0.020705975152829816,"losses":12744,"maximum_drawdown_pct":99.99999963837031,"mfe_reached_1r":2075,"mfe_reached_2r":652,"net_r":-7759.336964737538,"pair_count":68,"pair_distribution":{"AUD_CAD":238,"AUD_CHF":204,"AUD_HKD":239,"AUD_JPY":227,"AUD_NZD":211,"AUD_SGD":211,"AUD_USD":243,"CAD_CHF":240,"CAD_HKD":267,"CAD_JPY":231,"CAD_SGD":254,"CHF_HKD":250,"CHF_JPY":226,"CHF_ZAR":188,"EUR_AUD":228,"EUR_CAD":200,"EUR_CHF":223,"EUR_CZK":240,"EUR_DKK":217,"EUR_GBP":216,"EUR_HKD":244,"EUR_HUF":225,"EUR_JPY":208,"EUR_NOK":242,"EUR_NZD":229,"EUR_PLN":245,"EUR_SEK":238,"EUR_SGD":194,"EUR_TRY":87,"EUR_USD":237,"EUR_ZAR":200,"GBP_AUD":207,"GBP_CAD":218,"GBP_CHF":202,"GBP_HKD":244,"GBP_JPY":217,"GBP_NZD":225,"GBP_PLN":207,"GBP_SGD":225,"GBP_USD":237,"GBP_ZAR":185,"HKD_JPY":230,"NZD_CAD":227,"NZD_CHF":211,"NZD_HKD":252,"NZD_JPY":237,"NZD_SGD":243,"NZD_USD":241,"SGD_CHF":206,"SGD_JPY":196,"TRY_JPY":50,"USD_CAD":248,"USD_CHF":248,"USD_CNH":240,"USD_CZK":249,"USD_DKK":241,"USD_HKD":315,"USD_HUF":233,"USD_JPY":227,"USD_MXN":241,"USD_NOK":255,"USD_PLN":241,"USD_SEK":250,"USD_SGD":246,"USD_THB":265,"USD_TRY":69,"USD_ZAR":219,"ZAR_JPY":264},"profit_factor":0.20907548902572973,"session_distribution":{"ASIA":4593,"LONDON":3891,"NEW_YORK":4600,"ROLLOVER":2129},"trades":15213,"win_rate":0.1622954052455137,"wins":2469}`

Development SHORT: `{"average_loss_r":-0.7773800094248907,"average_win_r":0.9024778222342389,"ending_equity":0.00023836699194800396,"exit_reasons":{"SUPERTREND_STOP":14511,"TAKE_PROFIT":712},"expectancy_r":-0.5207059427863087,"largest_pair_share":0.020758063456611707,"losses":12897,"maximum_drawdown_pct":99.99999976163302,"mfe_reached_1r":2067,"mfe_reached_2r":746,"net_r":-7926.706567035977,"pair_count":68,"pair_distribution":{"AUD_CAD":237,"AUD_CHF":204,"AUD_HKD":239,"AUD_JPY":228,"AUD_NZD":211,"AUD_SGD":210,"AUD_USD":244,"CAD_CHF":240,"CAD_HKD":267,"CAD_JPY":231,"CAD_SGD":254,"CHF_HKD":251,"CHF_JPY":226,"CHF_ZAR":189,"EUR_AUD":228,"EUR_CAD":201,"EUR_CHF":222,"EUR_CZK":241,"EUR_DKK":217,"EUR_GBP":217,"EUR_HKD":245,"EUR_HUF":226,"EUR_JPY":209,"EUR_NOK":242,"EUR_NZD":230,"EUR_PLN":245,"EUR_SEK":238,"EUR_SGD":193,"EUR_TRY":85,"EUR_USD":238,"EUR_ZAR":200,"GBP_AUD":207,"GBP_CAD":219,"GBP_CHF":202,"GBP_HKD":244,"GBP_JPY":216,"GBP_NZD":226,"GBP_PLN":208,"GBP_SGD":225,"GBP_USD":237,"GBP_ZAR":185,"HKD_JPY":231,"NZD_CAD":226,"NZD_CHF":210,"NZD_HKD":252,"NZD_JPY":238,"NZD_SGD":243,"NZD_USD":241,"SGD_CHF":206,"SGD_JPY":196,"TRY_JPY":50,"USD_CAD":248,"USD_CHF":247,"USD_CNH":241,"USD_CZK":249,"USD_DKK":241,"USD_HKD":316,"USD_HUF":233,"USD_JPY":228,"USD_MXN":241,"USD_NOK":256,"USD_PLN":241,"USD_SEK":250,"USD_SGD":246,"USD_THB":265,"USD_TRY":68,"USD_ZAR":220,"ZAR_JPY":263},"profit_factor":0.20937468951614302,"session_distribution":{"ASIA":4585,"LONDON":3885,"NEW_YORK":4635,"ROLLOVER":2118},"trades":15223,"win_rate":0.1527951126584773,"wins":2326}`

## Alternative Family Inventory And Baselines

### MEAN_REVERSION_V1
- LONG: development expectancy `-0.316067R`, PF `0.5015867527006832`, drawdown `4.703348%`; provisional expectancy `-0.445612R`, PF `0.37884321366730045`, drawdown `7.055788%`; finalist eligible `False`.
- SHORT: development expectancy `-0.345438R`, PF `0.4762715340791193`, drawdown `5.455311%`; provisional expectancy `-0.590799R`, PF `0.24509070163787275`, drawdown `3.346673%`; finalist eligible `False`.
### DAY_TRADING_BREAKOUT_V1
- LONG: development expectancy `-0.310337R`, PF `0.4705919845367447`, drawdown `99.428536%`; provisional expectancy `-0.294557R`, PF `0.49101904544124164`, drawdown `92.506545%`; finalist eligible `False`.
- SHORT: development expectancy `-0.343928R`, PF `0.4300762226568448`, drawdown `99.719281%`; provisional expectancy `-0.332255R`, PF `0.4433246469094411`, drawdown `94.856554%`; finalist eligible `False`.

Family priority hash: `cacade59695ecd0ac5bee57095d46e9ad2607c909304e36a3f12afa6b03053dc`.

Finalists: `[]`.

Status: `NO_CANDIDATE_NEW_FORWARD_CYCLE_REQUIRED`. No candidate implementation, PAPER campaign, or LIVE action is permitted without genuinely new forward evidence and all later gates.
