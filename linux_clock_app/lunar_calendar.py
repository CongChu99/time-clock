"""Vietnamese Lunar Calendar conversion (HH algorithm by Ho Nguyen Hieu)."""
from __future__ import annotations

import math

_TZ = 7  # Vietnam UTC+7

_CAN = ["Giáp", "Ất", "Bính", "Đinh", "Mậu", "Kỷ", "Canh", "Tân", "Nhâm", "Quý"]
_CHI = ["Tý", "Sửu", "Dần", "Mão", "Thìn", "Tỵ", "Ngọ", "Mùi", "Thân", "Dậu", "Tuất", "Hợi"]

_DAY_NAMES = [
    "", "Mùng Một", "Mùng Hai", "Mùng Ba", "Mùng Bốn", "Mùng Năm",
    "Mùng Sáu", "Mùng Bảy", "Mùng Tám", "Mùng Chín", "Mùng Mười",
]


def _jd(d: int, m: int, y: int) -> int:
    """Gregorian date → Julian Day Number."""
    a = (14 - m) // 12
    yy = y + 4800 - a
    mm = m + 12 * a - 3
    jdn = d + (153 * mm + 2) // 5 + 365 * yy + yy // 4 - yy // 100 + yy // 400 - 32045
    if jdn < 2299161:
        jdn = d + (153 * mm + 2) // 5 + 365 * yy + yy // 4 - 32083
    return jdn


def _new_moon(k: int) -> int:
    """JDN of the k-th new moon after Jan 1900."""
    T = k / 1236.85
    T2 = T * T
    T3 = T2 * T
    dr = math.pi / 180
    jd1 = (2415020.75933 + 29.53058868 * k
           + 0.0001178 * T2 - 0.000000155 * T3
           + 0.00033 * math.sin((166.56 + 132.87 * T - 0.009173 * T2) * dr))
    M   = 359.2242   + 29.10535608  * k - 0.0000333  * T2 - 0.00000347  * T3
    Mpr = 306.0253   + 385.81691806 * k + 0.0107306  * T2 + 0.00001236  * T3
    F   = 21.2964    + 390.67050646 * k - 0.0016528  * T2 - 0.00000239  * T3
    C1  = ((0.1734 - 0.000393 * T) * math.sin(M * dr)
           + 0.0021 * math.sin(2 * M * dr)
           - 0.4068 * math.sin(Mpr * dr)
           + 0.0161 * math.sin(2 * Mpr * dr)
           - 0.0004 * math.sin(3 * Mpr * dr)
           + 0.0104 * math.sin(2 * F * dr)
           - 0.0051 * math.sin((M + Mpr) * dr)
           - 0.0074 * math.sin((M - Mpr) * dr)
           + 0.0004 * math.sin((2 * F + M) * dr)
           - 0.0004 * math.sin((2 * F - M) * dr)
           - 0.0006 * math.sin((2 * F + Mpr) * dr)
           + 0.0010 * math.sin((2 * F - Mpr) * dr)
           + 0.0005 * math.sin((M + 2 * Mpr) * dr))
    if T < -11:
        delta = (0.001 + 0.000839 * T + 0.0002261 * T2
                 - 0.00000845 * T3 - 0.000000081 * T * T3)
    else:
        delta = -0.000278 + 0.000265 * T + 0.000262 * T2
    return int(jd1 + C1 - delta + 0.5 + _TZ / 24)


def _sun_long(jdn: int) -> int:
    """Sun longitude sector 0–11 at given JDN."""
    T = (jdn - 2451545.5 - _TZ / 24) / 36525
    T2 = T * T
    dr = math.pi / 180
    M  = 357.52910 + 35999.05030 * T - 0.0001559 * T2 - 0.00000048 * T * T2
    L0 = 280.46645 + 36000.76983 * T + 0.0003032 * T2
    DL = ((1.9146 - 0.004817 * T - 0.000014 * T2) * math.sin(M * dr)
          + (0.019993 - 0.000101 * T) * math.sin(2 * M * dr)
          + 0.00029 * math.sin(3 * M * dr))
    L = (L0 + DL) * dr % (2 * math.pi)
    return int(L / math.pi * 6)


def _month11_jd(year: int) -> int:
    """JDN of the start of the 11th lunar month in the given Gregorian year."""
    off = _jd(31, 12, year) - 2415021
    k = int(off / 29.530588853)
    nm = _new_moon(k)
    if _sun_long(nm) >= 9:
        nm = _new_moon(k - 1)
    return nm


def _leap_month_offset(a11: int) -> int:
    """Index of the leap month in the lunar year starting at a11."""
    k = int(0.5 + (a11 - 2415021.076998695) / 29.530588853)
    last = 0
    i = 1
    arc = _sun_long(_new_moon(k + i))
    while True:
        last = arc
        i += 1
        arc = _sun_long(_new_moon(k + i))
        if arc == last or i >= 14:
            break
    return i - 1


def solar_to_lunar(d: int, m: int, y: int) -> tuple[int, int, int, bool]:
    """Convert Gregorian date to Vietnamese lunar date.

    Returns (lunar_day, lunar_month, lunar_year, is_leap_month).
    """
    jdn = _jd(d, m, y)
    k = int((jdn - 2415021.076998695) / 29.530588853)
    ms = _new_moon(k + 1)
    if ms > jdn:
        ms = _new_moon(k)

    a11 = _month11_jd(y)
    b11 = a11
    if a11 >= ms:
        ly = y
        a11 = _month11_jd(y - 1)
    else:
        ly = y + 1
        b11 = _month11_jd(y + 1)

    lday = jdn - ms + 1
    diff = int((ms - a11) / 29)
    leap = False
    lm = diff + 11

    if b11 - a11 > 365:
        leap_off = _leap_month_offset(a11)
        if diff >= leap_off:
            lm = diff + 10
            leap = (diff == leap_off)

    if lm > 12:
        lm -= 12
    if lm >= 11 and diff < 4:
        ly -= 1

    return lday, lm, ly, leap


def can_chi_year(lunar_year: int) -> str:
    """Return the can-chi name for *lunar_year*, e.g. ``'Ất Tỵ'``."""
    can = _CAN[(lunar_year + 6) % 10]
    chi = _CHI[(lunar_year + 8) % 12]
    return f"{can} {chi}"


def format_lunar_date(lday: int, lmonth: int, lyear: int, is_leap: bool) -> str:
    """Format a compact Vietnamese lunar date string.

    Examples: ``'ÂL: Mùng Ba/2 Ất Tỵ'``, ``'ÂL: 15/3 Bính Ngọ'``
    """
    day_str = _DAY_NAMES[lday] if lday <= 10 else str(lday)
    leap_str = "Nhuận " if is_leap else ""
    month_str = f"{leap_str}{lmonth}"
    year_str = can_chi_year(lyear)
    return f"ÂL: {day_str}/{month_str} {year_str}"
