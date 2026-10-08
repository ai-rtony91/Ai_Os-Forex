"""Fixed, one-attempt OANDA Practice EUR_USD M5 candle transport."""
from __future__ import annotations

import json
import math
import urllib.parse
import urllib.request
from typing import Any

TRANSPORT_IDENTITY = "AIOS_OANDA_PRACTICE_CANDLE_HISTORY_TRANSPORT.v1"
HOST = "api-fxpractice.oanda.com"
PATH = "/v3/instruments/EUR_USD/candles"
QUERY = {"granularity": "M5", "price": "M", "count": "50"}
URL = "https://" + HOST + PATH + "?" + urllib.parse.urlencode(QUERY)
TIMEOUT_SECONDS = 10


class CandleTransportError(ValueError):
    """Sanitized public transport failure."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        raise CandleTransportError("redirect_rejected")


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CandleTransportError("duplicate_json_key")
        result[key] = value
    return result


def _finite(value: str) -> None:
    raise CandleTransportError("non_finite_json")


def _validate_final_url(value: str) -> None:
    parsed = urllib.parse.urlsplit(value)
    if (parsed.scheme, parsed.hostname, parsed.port, parsed.path) != ("https", HOST, None, PATH):
        raise CandleTransportError("final_url_rejected")
    query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    if query != {key: [item] for key, item in QUERY.items()}:
        raise CandleTransportError("final_url_rejected")


def _sanitize(raw: bytes) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_finite)
    except CandleTransportError:
        raise
    except Exception as exc:
        raise CandleTransportError("invalid_json") from None
    if not isinstance(value, dict) or set(value) != {"instrument", "granularity", "candles"}:
        raise CandleTransportError("response_schema_rejected")
    if value["instrument"] != "EUR_USD" or value["granularity"] != "M5" or not isinstance(value["candles"], list):
        raise CandleTransportError("response_schema_rejected")
    candles = []
    for candle in value["candles"]:
        if not isinstance(candle, dict) or set(candle) != {"time", "complete", "volume", "mid"}:
            raise CandleTransportError("candle_schema_rejected")
        mid = candle["mid"]
        if not isinstance(mid, dict) or set(mid) != {"o", "h", "l", "c"}:
            raise CandleTransportError("midpoint_schema_rejected")
        if any(isinstance(v, float) and not math.isfinite(v) for v in mid.values()):
            raise CandleTransportError("non_finite_json")
        candles.append({"time": candle["time"], "complete": candle["complete"],
                        "volume": candle["volume"], "mid": dict(mid)})
    return {"instrument": "EUR_USD", "granularity": "M5", "candles": candles}


class OandaPracticeCandleHistoryTransportV1:
    """Capability-minimal transport: the sole operation is one fixed candle fetch."""

    identity = TRANSPORT_IDENTITY

    def __init__(self, api_token: str, *, opener: Any | None = None) -> None:
        if not isinstance(api_token, str) or not api_token:
            raise CandleTransportError("runtime_token_required")
        self.__token = api_token
        self.__opener = opener or urllib.request.build_opener(_NoRedirect())
        self.__attempted = False

    def __repr__(self) -> str:
        return f"{type(self).__name__}(request_budget_remaining={int(not self.__attempted)})"

    def fetch_eurusd_m5_midpoint_candles(self) -> dict[str, Any]:
        if self.__attempted:
            raise CandleTransportError("request_budget_consumed")
        request = urllib.request.Request(URL, method="GET", headers={"Authorization": "Bearer " + self.__token})
        self.__attempted = True
        try:
            response = self.__opener.open(request, timeout=TIMEOUT_SECONDS)
            _validate_final_url(response.geturl())
            return _sanitize(response.read())
        except CandleTransportError:
            raise
        except Exception:
            raise CandleTransportError("practice_candle_request_failed") from None
