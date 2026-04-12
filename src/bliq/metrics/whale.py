"""Whale detection signal factors.

Analyzes order book snapshots and trade flow to identify potential whale
activity. Each factor returns a WhaleSignal when triggered.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from bliq.data.binance_ws import AggTrade
from bliq.metrics.types import LiquidityReport


@dataclass(frozen=True, slots=True)
class WhaleSignal:
    """A detected whale activity signal."""

    symbol: str
    signal_type: str  # obi_shift, depth_pulse, large_trade, cvd_surge, cap_asymmetry
    side: str  # "buy" or "sell"
    strength: float  # 0-1, higher = stronger signal
    description: str
    ts_ms: int


# ---------------------------------------------------------------------------
# Factor 1: OBI Shift — detect sudden order book imbalance changes
# ---------------------------------------------------------------------------


def detect_obi_shift(
    current: LiquidityReport,
    previous: LiquidityReport,
    *,
    threshold: float = 0.4,
) -> WhaleSignal | None:
    """Alert when OBI-5 shifts by more than `threshold` between snapshots."""
    cur_obi = current.obi.by_levels.get(5, 0.0)
    prev_obi = previous.obi.by_levels.get(5, 0.0)
    delta = cur_obi - prev_obi

    if abs(delta) < threshold:
        return None

    side = "buy" if delta > 0 else "sell"
    strength = min(abs(delta) / 1.0, 1.0)
    return WhaleSignal(
        symbol=current.symbol,
        signal_type="obi_shift",
        side=side,
        strength=strength,
        description=(
            f"OBI-5 shifted {prev_obi:+.3f} -> {cur_obi:+.3f} "
            f"(delta={delta:+.3f}), large {side} orders appeared"
        ),
        ts_ms=current.ts_ms,
    )


# ---------------------------------------------------------------------------
# Factor 2: Depth Pulse — detect sudden depth concentration at a price level
# ---------------------------------------------------------------------------


def detect_depth_pulse(
    current: LiquidityReport,
    previous: LiquidityReport,
    *,
    ratio_threshold: float = 3.0,
) -> WhaleSignal | None:
    """Alert when depth at any band grows by more than `ratio_threshold`x."""
    for pct in current.depth.by_pct:
        cur_bid, cur_ask = current.depth.by_pct[pct]
        prev_bid, prev_ask = previous.depth.by_pct.get(pct, (0.0, 0.0))

        # Check bid side surge
        if prev_bid > 0 and cur_bid / prev_bid >= ratio_threshold:
            ratio = cur_bid / prev_bid
            return WhaleSignal(
                symbol=current.symbol,
                signal_type="depth_pulse",
                side="buy",
                strength=min(ratio / 10.0, 1.0),
                description=(
                    f"Bid depth at +/-{pct*100:.1f}% surged {ratio:.1f}x "
                    f"(${prev_bid:,.0f} -> ${cur_bid:,.0f})"
                ),
                ts_ms=current.ts_ms,
            )

        # Check ask side surge
        if prev_ask > 0 and cur_ask / prev_ask >= ratio_threshold:
            ratio = cur_ask / prev_ask
            return WhaleSignal(
                symbol=current.symbol,
                signal_type="depth_pulse",
                side="sell",
                strength=min(ratio / 10.0, 1.0),
                description=(
                    f"Ask depth at +/-{pct*100:.1f}% surged {ratio:.1f}x "
                    f"(${prev_ask:,.0f} -> ${cur_ask:,.0f})"
                ),
                ts_ms=current.ts_ms,
            )

    return None


# ---------------------------------------------------------------------------
# Factor 3: Cap Asymmetry — one side's capacity dwarfs the other
# ---------------------------------------------------------------------------


def detect_cap_asymmetry(
    report: LiquidityReport,
    *,
    ratio_threshold: float = 3.0,
) -> WhaleSignal | None:
    """Alert when buy/sell capacity ratio exceeds threshold."""
    cap_buy = report.slippage.capacity_buy_usdt
    cap_sell = report.slippage.capacity_sell_usdt

    if cap_sell <= 0 or cap_buy <= 0:
        return None

    if cap_buy / cap_sell >= ratio_threshold:
        ratio = cap_buy / cap_sell
        return WhaleSignal(
            symbol=report.symbol,
            signal_type="cap_asymmetry",
            side="buy",
            strength=min(ratio / 10.0, 1.0),
            description=(
                f"Buy capacity ${cap_buy:,.0f} vs sell ${cap_sell:,.0f} "
                f"({ratio:.1f}x), heavy bid-side liquidity"
            ),
            ts_ms=report.ts_ms,
        )

    if cap_sell / cap_buy >= ratio_threshold:
        ratio = cap_sell / cap_buy
        return WhaleSignal(
            symbol=report.symbol,
            signal_type="cap_asymmetry",
            side="sell",
            strength=min(ratio / 10.0, 1.0),
            description=(
                f"Sell capacity ${cap_sell:,.0f} vs buy ${cap_buy:,.0f} "
                f"({ratio:.1f}x), heavy ask-side liquidity"
            ),
            ts_ms=report.ts_ms,
        )

    return None


# ---------------------------------------------------------------------------
# Factor 4 & 5: Trade flow — large trades + CVD surge
# ---------------------------------------------------------------------------


@dataclass
class TradeFlowTracker:
    """Tracks trade flow for a single symbol to detect large trades and CVD surges.

    Maintains a rolling window of trades and computes cumulative volume delta.
    """

    symbol: str
    large_trade_threshold_usdt: float = 50_000.0
    cvd_window_seconds: float = 300.0  # 5 min rolling window
    cvd_surge_threshold_usdt: float = 200_000.0
    cvd_cooldown_seconds: float = 60.0  # only report CVD surge once per cooldown

    _trades: deque[AggTrade] = field(default_factory=deque)
    _cvd: float = 0.0  # cumulative volume delta in window
    _buy_volume: float = 0.0
    _sell_volume: float = 0.0
    _last_cvd_signal_ms: int = 0

    def _prune(self, now_ms: int) -> None:
        cutoff = now_ms - int(self.cvd_window_seconds * 1000)
        while self._trades and self._trades[0].ts_ms < cutoff:
            old = self._trades.popleft()
            if old.side == "buy":
                self._buy_volume -= old.notional
                self._cvd -= old.notional
            else:
                self._sell_volume -= old.notional
                self._cvd += old.notional

    def ingest(self, trade: AggTrade) -> list[WhaleSignal]:
        """Process a new trade. Returns any whale signals triggered."""
        signals: list[WhaleSignal] = []

        # Update rolling window
        self._trades.append(trade)
        if trade.side == "buy":
            self._buy_volume += trade.notional
            self._cvd += trade.notional
        else:
            self._sell_volume += trade.notional
            self._cvd -= trade.notional

        self._prune(trade.ts_ms)

        # Factor 4: Large single trade
        if trade.notional >= self.large_trade_threshold_usdt:
            signals.append(
                WhaleSignal(
                    symbol=self.symbol,
                    signal_type="large_trade",
                    side=trade.side,
                    strength=min(trade.notional / (self.large_trade_threshold_usdt * 10), 1.0),
                    description=(
                        f"Large {trade.side} trade: ${trade.notional:,.0f} "
                        f"({trade.qty:.4f} @ {trade.price:.4f})"
                    ),
                    ts_ms=trade.ts_ms,
                )
            )

        # Factor 5: CVD surge (with cooldown to avoid spam)
        cooldown_ms = int(self.cvd_cooldown_seconds * 1000)
        if (
            abs(self._cvd) >= self.cvd_surge_threshold_usdt
            and trade.ts_ms - self._last_cvd_signal_ms >= cooldown_ms
        ):
            side = "buy" if self._cvd > 0 else "sell"
            self._last_cvd_signal_ms = trade.ts_ms
            signals.append(
                WhaleSignal(
                    symbol=self.symbol,
                    signal_type="cvd_surge",
                    side=side,
                    strength=min(abs(self._cvd) / (self.cvd_surge_threshold_usdt * 5), 1.0),
                    description=(
                        f"CVD surge: ${self._cvd:+,.0f} over {self.cvd_window_seconds:.0f}s "
                        f"(buy=${self._buy_volume:,.0f} sell=${self._sell_volume:,.0f})"
                    ),
                    ts_ms=trade.ts_ms,
                )
            )

        return signals

    @property
    def cvd(self) -> float:
        return self._cvd

    @property
    def buy_volume(self) -> float:
        return self._buy_volume

    @property
    def sell_volume(self) -> float:
        return self._sell_volume
