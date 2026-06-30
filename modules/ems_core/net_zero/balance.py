def compute_rpnz_w(quarter_energy_balance_kwh: float, remaining_s: float) -> int:
    remaining_s = max(float(remaining_s), 30.0)
    return int(round(-(quarter_energy_balance_kwh * 3600.0 / remaining_s) * 1000.0))
