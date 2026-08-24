"""A-share fee model (simplified retail defaults)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FeeSchedule:
    commission_rate: float = 0.00025  # 万2.5
    commission_min: float = 5.0
    stamp_duty_rate: float = 0.0005  # 卖出千0.5（现行口径；可配置）
    transfer_fee_rate: float = 0.00001  # 过户费约万0.1（双边近似）


DEFAULT_FEES = FeeSchedule()


def calc_fees(side: str, notional: float, schedule: FeeSchedule = DEFAULT_FEES) -> dict[str, float]:
    commission = max(notional * schedule.commission_rate, schedule.commission_min)
    transfer = notional * schedule.transfer_fee_rate
    stamp = notional * schedule.stamp_duty_rate if side == "sell" else 0.0
    total = commission + transfer + stamp
    return {
        "commission": round(commission, 2),
        "transfer_fee": round(transfer, 2),
        "stamp_duty": round(stamp, 2),
        "total": round(total, 2),
    }
