"""GET-only OANDA read-only client.

The client uses Python standard library HTTP primitives and rejects every
non-GET method. It is intended for runtime use only after explicit read-only
enablement. Callers must sanitize all broker-derived payloads before display,
logging, or report writing.
"""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


PRACTICE_BASE_URL = "https://api-fxpractice.oanda.com"
LIVE_BASE_URL = "https://api-fxtrade.oanda.com"


class OandaReadOnlyClientError(RuntimeError):
    def __init__(self, public_reason: str, *, status_code: int | None = None) -> None:
        super().__init__(public_reason)
        self.public_reason = public_reason
        self.status_code = status_code


class ReadOnlyMethodRejected(OandaReadOnlyClientError):
    pass


class OandaReadOnlyClient:
    """Small OANDA REST client constrained to read-only GET requests."""

    def __init__(
        self,
        *,
        api_token: str,
        account_id: str,
        environment: str = "practice",
        timeout_seconds: int = 10,
        opener: Any | None = None,
    ) -> None:
        self._api_token = api_token
        self._account_id = account_id
        self.environment = _normalize_environment(environment)
        self.timeout_seconds = int(timeout_seconds)
        self._opener = opener
        self._base_url = LIVE_BASE_URL if self.environment == "live" else PRACTICE_BASE_URL

    def __repr__(self) -> str:
        return (
            "OandaReadOnlyClient(environment="
            f"{self.environment!r}, credential_status='PRESENT_OR_MISSING', account_id='MASKED')"
        )

    def request_json(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        method_upper = str(method or "").upper()
        if method_upper != "GET":
            raise ReadOnlyMethodRejected("Only GET requests are allowed by the read-only bridge")

        url = self._build_url(path, params=params)
        request = Request(
            url,
            headers={
                "Authorization": f"Bearer {self._api_token}",
                "Accept": "application/json",
            },
            method="GET",
        )
        try:
            opener = self._opener or urlopen
            with opener(request, timeout=self.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except HTTPError as exc:
            raise OandaReadOnlyClientError(
                "HTTP_ERROR_SANITIZED",
                status_code=exc.code,
            ) from exc
        except URLError as exc:
            raise OandaReadOnlyClientError("NETWORK_ERROR_SANITIZED") from exc

        try:
            payload = json.loads(raw or "{}")
        except json.JSONDecodeError as exc:
            raise OandaReadOnlyClientError("JSON_DECODE_ERROR_SANITIZED") from exc
        if not isinstance(payload, dict):
            raise OandaReadOnlyClientError("UNSUPPORTED_RESPONSE_SHAPE_SANITIZED")
        return payload

    def account_summary(self) -> dict[str, Any]:
        return self.request_json("GET", f"/v3/accounts/{self._account_id}/summary")

    def account_details(self) -> dict[str, Any]:
        return self.request_json("GET", f"/v3/accounts/{self._account_id}")

    def open_positions(self) -> dict[str, Any]:
        return self.request_json("GET", f"/v3/accounts/{self._account_id}/openPositions")

    def open_trades(self) -> dict[str, Any]:
        return self.request_json("GET", f"/v3/accounts/{self._account_id}/openTrades")

    def pending_orders(self) -> dict[str, Any]:
        return self.request_json("GET", f"/v3/accounts/{self._account_id}/pendingOrders")

    def pricing(self, instruments: tuple[str, ...]) -> dict[str, Any]:
        if not instruments or any(not isinstance(item, str) or not item for item in instruments):
            raise ValueError("pricing_instruments_required")
        return self.request_json(
            "GET",
            f"/v3/accounts/{self._account_id}/pricing",
            params={"instruments": ",".join(instruments)},
        )

    def discover_instruments(self) -> dict[str, Any]:
        """Read the account's enabled instrument universe through the GET-only bridge."""
        return self.request_json("GET", f"/v3/accounts/{self._account_id}/instruments")

    def observation_candles(
        self,
        instrument: str,
        *,
        granularity: str,
        count: int,
        price: str = "M",
    ) -> dict[str, Any]:
        """Observer-only completed-candle request.

        The legacy ``candles`` method retains its strict EUR_USD/M5 contract
        for the active campaign.  This separate method intentionally supports
        only the new observer's M1/M2/M5 read path and still performs GET only.
        """
        normalized_instrument = str(instrument or "").upper()
        if not re.fullmatch(r"[A-Z]{3}_[A-Z]{3}", normalized_instrument):
            raise ValueError("unsupported_observation_instrument")
        if granularity not in {"M1", "M2", "M5"}:
            raise ValueError("unsupported_observation_granularity")
        if isinstance(count, bool) or not isinstance(count, int) or not 5 <= count <= 501:
            raise ValueError("observation_candle_count_out_of_bounds")
        if price not in {"M", "MBA"}:
            raise ValueError("unsupported_observation_candle_price")
        return self.request_json(
            "GET",
            f"/v3/instruments/{normalized_instrument}/candles",
            params={"granularity": granularity, "count": count, "price": price},
        )

    def candles(
        self,
        instrument: str,
        *,
        granularity: str,
        count: int,
        price: str = "M",
    ) -> dict[str, Any]:
        """Fetch a bounded candle window through the GET-only transport."""
        if instrument != "EUR_USD":
            raise ValueError("unsupported_candle_instrument")
        if granularity != "M5":
            raise ValueError("unsupported_candle_granularity")
        if isinstance(count, bool) or not isinstance(count, int) or not 3 <= count <= 500:
            raise ValueError("candle_count_out_of_bounds")
        if price != "M":
            raise ValueError("unsupported_candle_price")
        return self.request_json(
            "GET",
            f"/v3/instruments/{instrument}/candles",
            params={"granularity": granularity, "count": count, "price": price},
        )

    def transactions(self) -> dict[str, Any]:
        return self.request_json(
            "GET",
            f"/v3/accounts/{self._account_id}/transactions",
            params={"type": "ORDER_FILL,TRADE_CLOSE"},
        )

    def fetch_read_only_snapshot(self, *, instruments: tuple[str, ...]) -> dict[str, Any]:
        snapshot: dict[str, Any] = {
            "environment": self.environment,
            "read_only": True,
            "write_methods_allowed": False,
        }
        calls = (
            ("account_summary", self.account_summary),
            ("account_details", self.account_details),
            ("open_positions", self.open_positions),
            ("open_trades", self.open_trades),
            ("pending_orders", self.pending_orders),
            ("pricing", lambda: self.pricing(instruments)),
            ("transactions", self.transactions),
        )
        for name, call in calls:
            try:
                snapshot[name] = call()
            except OandaReadOnlyClientError as exc:
                snapshot[name] = {
                    "error": exc.public_reason,
                    "status_code": exc.status_code,
                    "sanitized": True,
                }
        return snapshot

    def _build_url(self, path: str, *, params: dict[str, Any] | None = None) -> str:
        clean_path = "/" + str(path).lstrip("/")
        query = urlencode(params or {}, doseq=True)
        if query:
            return f"{self._base_url}{clean_path}?{query}"
        return f"{self._base_url}{clean_path}"


def _normalize_environment(value: str) -> str:
    normalized = str(value or "practice").strip().lower()
    if normalized == "live":
        return "live"
    return "practice"
