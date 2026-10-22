# AIOS Forex Profitability Readiness Scorecard V2

## OFFICIAL_DATA_CLOSURE

- score: 70
- evidence: HUMAN_OFFICIAL_DATA_DOWNLOAD_REQUIRED
- missing evidence: [{'expected_content_type': 'text/html', 'expected_destination_relative_path': '.aios/runtime/forex_official_data_breakthrough_v1/human_download_inbox/CENTRAL_BANK_POLICY_HISTORY_IUDERB', 'expected_time_period': '2005-01-01 through 2026-08-29', 'official_url': 'https://fred.stlouisfed.org/series/IUDERB', 'post_download_hash_status': 'PENDING_HUMAN_DOWNLOAD', 'private_account_required': False, 'secret_required': False, 'source_family_purpose': 'CENTRAL_BANK_POLICY_HISTORY', 'source_owner': 'Bank of England / FRED', 'validation_command': 'python -B automation/forex_engine/forex_external_information_corpus_v3.py --execute'}, {'expected_content_type': 'text/html', 'expected_destination_relative_path': '.aios/runtime/forex_official_data_breakthrough_v1/human_download_inbox/CFTC_POSITIONING_HISTORY_CFTC_historical_compressed_futures_only_Commitments_of_Traders', 'expected_time_period': '2005-01-01 through 2026-08-29', 'official_url': 'https://www.cftc.gov/MarketReports/CommitmentsofTraders/HistoricalCompressed/index.htm', 'post_download_hash_status': 'PENDING_HUMAN_DOWNLOAD', 'private_account_required': False, 'secret_required': False, 'source_family_purpose': 'CFTC_POSITIONING_HISTORY', 'source_owner': 'CFTC', 'validation_command': 'python -B automation/forex_engine/forex_external_information_corpus_v3.py --execute'}, {'expected_content_type': 'text/html', 'expected_destination_relative_path': '.aios/runtime/forex_official_data_breakthrough_v1/human_download_inbox/OFFICIAL_MACRO_RELEASE_SCHEDULES_BLS_public_release_calendars_and_archive', 'expected_time_period': '2005-01-01 through 2026-08-29', 'official_url': 'https://www.bls.gov/bls/news-release/home.htm', 'post_download_hash_status': 'PENDING_HUMAN_DOWNLOAD', 'private_account_required': False, 'secret_required': False, 'source_family_purpose': 'OFFICIAL_MACRO_RELEASE_SCHEDULES', 'source_owner': 'U.S. Bureau of Labor Statistics', 'validation_command': 'python -B automation/forex_engine/forex_external_information_corpus_v3.py --execute'}]
- unlock condition: complete consolidated public official download/import

## PRACTICE_HISTORY_BOUNDARY

- score: 80
- evidence: 0e5c3081a5116ec6dd4baf8a330079644703ab3af466b8c5373db33a3246cfd7
- missing evidence: Human-produced sanitized OANDA Practice artifacts
- unlock condition: run Human-only helper outside Codex

## MULTI_REGIME_CORPUS

- score: 0
- evidence: HUMAN_PRACTICE_DATA_ACQUISITION_REQUIRED
- missing evidence: Human-only OANDA Practice GET-only acquisition is required; Codex must not receive the Practice token or authorization header.
- unlock condition: sanitized artifacts imported and corpus frozen

## EXTERNAL_INFORMATION_CORPUS

- score: 86
- evidence: HUMAN_OFFICIAL_DATA_DOWNLOAD_REQUIRED
- missing evidence: 3
- unlock condition: freeze External Information Corpus V3

## RESEARCH_PIPELINE_FALSIFIABILITY

- score: 0
- evidence: not run
- missing evidence: PC/NC controls
- unlock condition: data blockers closed

## LONG_HISTORICAL_EDGE

- score: 0
- evidence: not run
- missing evidence: Development/Validation/Holdout/recent PASS
- unlock condition: data + falsifiability PASS

## SHORT_HISTORICAL_EDGE

- score: 0
- evidence: not run
- missing evidence: Development/Validation/Holdout/recent PASS
- unlock condition: data + falsifiability PASS

## LONG_FORWARD

- score: 0
- evidence: not started
- missing evidence: 30 trades and maturity
- unlock condition: LONG finalist

## SHORT_FORWARD

- score: 0
- evidence: not started
- missing evidence: 30 trades and maturity
- unlock condition: SHORT finalist

## BIDIRECTIONAL_PAPER

- score: 0
- evidence: not started
- missing evidence: LONG and SHORT Paper PASS
- unlock condition: both directions Forward PASS

## FUNDING_READINESS

- score: 0
- evidence: not reached
- missing evidence: publication/live-safety/credential/funding gates
- unlock condition: bidirectional Paper + publication + live safety
