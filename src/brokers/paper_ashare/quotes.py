"""Pluggable last-price feeds for paper matching."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional, Protocol

import requests

from .paths import load_secrets_into_environ


@dataclass(frozen=True)
class Quote:
    symbol: str  # normalized 600519.SH
    last: float
    prev_close: Optional[float] = None
    source: str = "unknown"
    asof_ms: Optional[int] = None


class QuoteFeed(Protocol):
    def get_quote(self, symbol: str) -> Quote: ...


def normalize_symbol(code: str) -> str:
    raw = code.strip().upper().replace(" ", "")
    if not raw:
        raise ValueError("empty symbol")
    if "." in raw:
        return raw
    if raw.startswith(("SH", "SZ", "BJ")) and len(raw) > 2 and raw[2:].isdigit():
        return f"{raw[2:]}.{raw[:2]}"
    if raw.isdigit() and len(raw) == 6:
        if raw.startswith(("5", "6", "9")):
            return f"{raw}.SH"
        return f"{raw}.SZ"
    return raw


def to_secid(symbol: str) -> str:
    """Eastmoney secid: 1.SH / 0.SZ / 0.BJ heuristic."""
    sym = normalize_symbol(symbol)
    code, mkt = sym.split(".", 1)
    if mkt == "SH":
        return f"1.{code}"
    if mkt == "BJ":
        return f"0.{code}"
    return f"0.{code}"


class FixedQuoteFeed:
    def __init__(self, prices: dict[str, float]):
        self.prices = {normalize_symbol(k): float(v) for k, v in prices.items()}

    def get_quote(self, symbol: str) -> Quote:
        sym = normalize_symbol(symbol)
        if sym not in self.prices:
            raise KeyError(f"no fixed price for {sym}")
        return Quote(symbol=sym, last=self.prices[sym], source="fixed")


class FuyaoQuoteFeed:
    def __init__(self, timeout: float = 15.0):
        load_secrets_into_environ()
        from marketdata.fuyao.client import FuyaoClient

        self._client = FuyaoClient(timeout=timeout)

    def get_quote(self, symbol: str) -> Quote:
        sym = normalize_symbol(symbol)
        payload = self._client.snapshot([sym])
        items = ((payload.get("data") or {}).get("item")) or []
        if not items:
            raise RuntimeError(f"fuyao empty snapshot for {sym}")
        item = items[0]
        last = float(item["last_price"])
        prev = item.get("prev_price")
        return Quote(
            symbol=sym,
            last=last,
            prev_close=float(prev) if prev is not None else None,
            source="fuyao",
            asof_ms=(payload.get("data") or {}).get("timestamp"),
        )


_UA = {
    "User-Agent": "Mozilla/5.0 (compatible; magellen-paper-ashare/0.1; +local)",
    "Referer": "https://quote.eastmoney.com/",
}


class EastmoneyQuoteFeed:
    """Public snapshot fallback (no key). Latency usually seconds; OK for ≤30s paper."""

    HOSTS = (
        "https://push2.eastmoney.com/api/qt/stock/get",
        "https://push2delay.eastmoney.com/api/qt/stock/get",
    )

    def __init__(self, timeout: float = 10.0, cache_ttl: float = 15.0):
        self.timeout = timeout
        self.cache_ttl = cache_ttl
        self._cache: dict[str, tuple[float, Quote]] = {}

    def get_quote(self, symbol: str) -> Quote:
        sym = normalize_symbol(symbol)
        now = time.time()
        hit = self._cache.get(sym)
        if hit and now - hit[0] < self.cache_ttl:
            return hit[1]

        secid = to_secid(sym)
        params = {
            "secid": secid,
            "fields": "f43,f57,f58,f60,f169,f170",
            "fltt": "2",
        }
        errors: list[str] = []
        for url in self.HOSTS:
            try:
                response = requests.get(
                    url, params=params, timeout=self.timeout, headers=_UA
                )
                response.raise_for_status()
                data = (response.json() or {}).get("data") or {}
                last = data.get("f43")
                if last is None:
                    errors.append(f"{url}: empty last")
                    continue
                prev = data.get("f60")
                quote = Quote(
                    symbol=sym,
                    last=float(last),
                    prev_close=float(prev) if prev is not None else None,
                    source="eastmoney",
                    asof_ms=int(now * 1000),
                )
                self._cache[sym] = (now, quote)
                return quote
            except Exception as e:
                errors.append(f"{url}: {e}")
        raise RuntimeError("; ".join(errors))


class SinaQuoteFeed:
    """Secondary public fallback."""

    def __init__(self, timeout: float = 10.0, cache_ttl: float = 15.0):
        self.timeout = timeout
        self.cache_ttl = cache_ttl
        self._cache: dict[str, tuple[float, Quote]] = {}

    def get_quote(self, symbol: str) -> Quote:
        sym = normalize_symbol(symbol)
        now = time.time()
        hit = self._cache.get(sym)
        if hit and now - hit[0] < self.cache_ttl:
            return hit[1]
        code, mkt = sym.split(".", 1)
        sina_code = f"{'sh' if mkt == 'SH' else 'sz'}{code}"
        url = f"https://hq.sinajs.cn/list={sina_code}"
        response = requests.get(
            url,
            timeout=self.timeout,
            headers={
                "User-Agent": _UA["User-Agent"],
                "Referer": "https://finance.sina.com.cn/",
            },
        )
        response.raise_for_status()
        text = response.content.decode("gbk", errors="replace")
        # var hq_str_sh600519="name,open,prev,last,...";
        if "=" not in text or '"' not in text:
            raise RuntimeError(f"sina bad body for {sym}")
        payload = text.split('"', 2)[1]
        parts = payload.split(",")
        if len(parts) < 4 or not parts[3]:
            raise RuntimeError(f"sina empty quote for {sym}: {payload!r}")
        last = float(parts[3])
        prev = float(parts[2]) if parts[2] else None
        quote = Quote(
            symbol=sym,
            last=last,
            prev_close=prev,
            source="sina",
            asof_ms=int(now * 1000),
        )
        self._cache[sym] = (now, quote)
        return quote


class CascadingQuoteFeed:
    """Try Fuyao (if keyed) → Eastmoney → Sina."""

    def __init__(self, timeout: float = 15.0):
        self.timeout = timeout
        self._fuyao: Optional[FuyaoQuoteFeed] = None
        self._em = EastmoneyQuoteFeed(timeout=timeout)
        self._sina = SinaQuoteFeed(timeout=timeout)
        try:
            load_secrets_into_environ()
            from marketdata.fuyao.secrets import resolve_api_key

            if resolve_api_key():
                self._fuyao = FuyaoQuoteFeed(timeout=timeout)
        except Exception:
            self._fuyao = None

    def get_quote(self, symbol: str) -> Quote:
        errors: list[str] = []
        if self._fuyao is not None:
            try:
                return self._fuyao.get_quote(symbol)
            except Exception as e:
                errors.append(f"fuyao: {e}")
        try:
            return self._em.get_quote(symbol)
        except Exception as e:
            errors.append(f"eastmoney: {e}")
        try:
            return self._sina.get_quote(symbol)
        except Exception as e:
            errors.append(f"sina: {e}")
        raise RuntimeError("; ".join(errors) or "no quote feed")
