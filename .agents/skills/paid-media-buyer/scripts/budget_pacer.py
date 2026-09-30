#!/usr/bin/env python3
"""Crewloom paid-media-buyer — daily budget pacing check.

Compares actual spend-to-date against the expected pace for a campaign's
approved daily budget (from Campaign_Brief_Template.md), so over/under-spend
is caught with a real number instead of a guess.
"""
import argparse
import sys


def pace_check(daily_budget: float, days_elapsed: int, actual_spend: float) -> None:
    if daily_budget <= 0 or days_elapsed <= 0:
        print("خطأ: الميزانية اليومية وعدد الأيام يجب أن يكونا أكبر من صفر.", file=sys.stderr)
        sys.exit(1)
    expected_spend = daily_budget * days_elapsed
    diff = actual_spend - expected_spend
    diff_pct = (diff / expected_spend * 100) if expected_spend else 0.0

    print(f"\n=== فحص وتيرة الإنفاق — يوم {days_elapsed} ===\n")
    print(f"  الميزانية اليومية المعتمدة: {daily_budget:,.2f}")
    print(f"  الإنفاق المتوقع حتى الآن: {expected_spend:,.2f}")
    print(f"  الإنفاق الفعلي: {actual_spend:,.2f}")
    print(f"  الفرق: {diff:+,.2f} ({diff_pct:+.1f}%)")

    if abs(diff_pct) <= 10:
        print("\n  ✅ الوتيرة طبيعية (ضمن ±10% من المخطط).")
    elif diff_pct > 10:
        print("\n  ⚠️ إنفاق أسرع من المخطط — راجع الـbidding قبل نفاد الميزانية الشهرية مبكراً.")
    else:
        print("\n  ⚠️ إنفاق أبطأ من المخطط — راجع استهداف/موافقة الإعلان، الميزانية مش بتُستهلك كامل.")


def main() -> int:
    p = argparse.ArgumentParser(description="Crewloom ad spend pacing checker")
    p.add_argument("--daily-budget", type=float, required=True, help="الميزانية اليومية المعتمدة في Campaign Brief")
    p.add_argument("--days-elapsed", type=int, required=True, help="عدد أيام الحملة حتى الآن")
    p.add_argument("--actual-spend", type=float, required=True, help="الإنفاق الفعلي الظاهر في لوحة الإعلانات")
    args = p.parse_args()
    pace_check(args.daily_budget, args.days_elapsed, args.actual_spend)
    return 0


if __name__ == "__main__":
    sys.exit(main())
