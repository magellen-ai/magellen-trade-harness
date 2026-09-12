"""Unit tests for OKX service layer (no live network)."""

from __future__ import annotations

import json
import unittest
from typing import Any, Optional
from unittest.mock import MagicMock

from brokers.okx.client import OkxRestClient, sign
from brokers.okx.service import OkxService
from brokers.okx.types import AlgoOrderRequest, AttachTpSl, OrderRequest, oco_tp_sl, stop_loss


class FakeResponse:
    def __init__(self, payload: dict[str, Any], status_code: int = 200):
        self._payload = payload
        self.status_code = status_code
        self.text = json.dumps(payload)

    def json(self) -> dict[str, Any]:
        return self._payload


class OkxTypesTest(unittest.TestCase):
    def test_market_order_payload(self) -> None:
        body = OrderRequest(
            inst_id="BTC-USDT",
            side="buy",
            sz="0.01",
            td_mode="cash",
            ord_type="market",
        ).to_payload()
        self.assertEqual(body["instId"], "BTC-USDT")
        self.assertEqual(body["ordType"], "market")
        self.assertNotIn("px", body)

    def test_limit_requires_px(self) -> None:
        with self.assertRaises(ValueError):
            OrderRequest(
                inst_id="BTC-USDT",
                side="buy",
                sz="0.01",
                ord_type="limit",
            ).to_payload()

    def test_attach_tp_sl(self) -> None:
        body = OrderRequest(
            inst_id="BTC-USDT",
            side="buy",
            sz="0.01",
            ord_type="limit",
            px="60000",
            attach_tp_sl=AttachTpSl(
                tp_trigger_px="65000",
                tp_ord_px="-1",
                sl_trigger_px="55000",
                sl_ord_px="-1",
            ),
        ).to_payload()
        self.assertIn("attachAlgoOrds", body)
        self.assertEqual(body["attachAlgoOrds"][0]["slTriggerPx"], "55000")

    def test_stop_loss_helper(self) -> None:
        algo = stop_loss(
            inst_id="BTC-USDT-SWAP",
            side="sell",
            sz="1",
            trigger_px="50000",
            td_mode="cross",
        )
        body = algo.to_payload()
        self.assertEqual(body["ordType"], "conditional")
        self.assertEqual(body["slTriggerPx"], "50000")
        self.assertEqual(body["slOrdPx"], "-1")
        self.assertTrue(body["reduceOnly"])

    def test_oco_requires_both_legs(self) -> None:
        with self.assertRaises(ValueError):
            AlgoOrderRequest(
                inst_id="BTC-USDT",
                side="sell",
                sz="0.01",
                ord_type="oco",
                tp_trigger_px="70000",
                tp_ord_px="-1",
            ).to_payload()

    def test_oco_helper(self) -> None:
        body = oco_tp_sl(
            inst_id="BTC-USDT",
            side="sell",
            sz="0.01",
            tp_trigger_px="70000",
            sl_trigger_px="50000",
        ).to_payload()
        self.assertEqual(body["ordType"], "oco")
        self.assertEqual(body["tpTriggerPx"], "70000")
        self.assertEqual(body["slTriggerPx"], "50000")


class OkxSignTest(unittest.TestCase):
    def test_sign_stable(self) -> None:
        # Known vector: message construction only; hash must be deterministic.
        a = sign("secret", "2020-12-08T09:08:57.715Z", "GET", "/api/v5/account/balance", "")
        b = sign("secret", "2020-12-08T09:08:57.715Z", "GET", "/api/v5/account/balance", "")
        self.assertEqual(a, b)
        self.assertTrue(a)


class OkxServiceTest(unittest.TestCase):
    def _client(self, responder) -> OkxRestClient:
        session = MagicMock()
        session.request.side_effect = responder
        return OkxRestClient(
            api_key="k",
            api_secret="s",
            passphrase="p",
            simulated=True,
            session=session,
        )

    def test_dry_run_order_does_not_hit_network(self) -> None:
        calls: list[Any] = []

        def responder(*_a: Any, **_k: Any) -> FakeResponse:
            calls.append(1)
            return FakeResponse({"code": "0", "data": []})

        svc = OkxService(self._client(responder), default_dry_run=True)
        out = svc.place_order(
            OrderRequest(inst_id="BTC-USDT", side="buy", sz="0.01", td_mode="cash")
        )
        self.assertTrue(out["dry_run"])
        self.assertEqual(out["payload"]["instId"], "BTC-USDT")
        self.assertIn("clOrdId", out["payload"])
        self.assertEqual(calls, [])

    def test_live_order_posts(self) -> None:
        def responder(method: str, url: str, **kwargs: Any) -> FakeResponse:
            self.assertEqual(method, "POST")
            self.assertIn("/api/v5/trade/order", url)
            headers = kwargs.get("headers") or {}
            self.assertEqual(headers.get("x-simulated-trading"), "1")
            self.assertIn("OK-ACCESS-SIGN", headers)
            return FakeResponse(
                {
                    "code": "0",
                    "data": [{"ordId": "1", "clOrdId": "abc", "sCode": "0", "sMsg": ""}],
                }
            )

        svc = OkxService(self._client(responder), default_dry_run=True)
        out = svc.place_order(
            OrderRequest(inst_id="BTC-USDT", side="buy", sz="0.01"),
            dry_run=False,
        )
        self.assertTrue(out["success"])
        self.assertEqual(out["ord_id"], "1")
        self.assertTrue(out["simulated"])

    def test_place_algo_sl_dry_run(self) -> None:
        svc = OkxService(
            self._client(lambda *_a, **_k: FakeResponse({"code": "0", "data": []})),
            default_dry_run=True,
        )
        out = svc.place_stop_loss(
            inst_id="BTC-USDT",
            side="sell",
            sz="0.01",
            trigger_px="50000",
        )
        self.assertTrue(out["dry_run"])
        self.assertEqual(out["payload"]["ordType"], "conditional")
        self.assertEqual(out["payload"]["slTriggerPx"], "50000")

    def test_ticker_public_no_auth_headers(self) -> None:
        captured: dict[str, Any] = {}

        def responder(method: str, url: str, **kwargs: Any) -> FakeResponse:
            captured["headers"] = kwargs.get("headers") or {}
            return FakeResponse(
                {"code": "0", "data": [{"instId": "BTC-USDT", "last": "60000"}]}
            )

        # Public call: auth=False → no OK-ACCESS-* required even with empty creds.
        session = MagicMock()
        session.request.side_effect = responder
        client = OkxRestClient(
            api_key=None,
            api_secret=None,
            passphrase=None,
            simulated=True,
            session=session,
        )
        svc = OkxService(client)
        row = svc.ticker("BTC-USDT")
        self.assertEqual(row["last"], "60000")
        self.assertNotIn("OK-ACCESS-KEY", captured["headers"])
        self.assertEqual(captured["headers"].get("x-simulated-trading"), "1")

    def test_api_error_raises(self) -> None:
        def responder(*_a: Any, **_k: Any) -> FakeResponse:
            return FakeResponse({"code": "50111", "msg": "Invalid OK-ACCESS-KEY"}, status_code=401)

        client = self._client(responder)
        with self.assertRaises(Exception) as ctx:
            client.get("/api/v5/account/balance")
        self.assertIn("50111", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
