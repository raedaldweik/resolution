"""Demo citizen registry — the system-of-record stand-in the Customer
Resolution agent reads. Two cases matching the published decision flow's
test data: Fatima (suspended, verification expired) and Ahmed (over the
income threshold)."""

CITIZENS = {
    "784-1985-9384756-1": {
        "emiratesId": "784-1985-9384756-1",
        "nameEn": "Fatima Al Mansoori", "nameAr": "فاطمة المنصوري",
        "nationality": "UAE", "emirate": "Sharjah", "familySize": 5,
        "employment": {"status": "Employed", "employer": "Al Noor Trading LLC",
                       "declaredMonthlyIncomeAED": None,
                       "incomeVerifiedUntil": "2026-03-31"},
        "benefit": {"program": "Inflation Allowance", "status": "SUSPENDED",
                    "statusReason": "INCOME_VERIFICATION_EXPIRED",
                    "suspendedSince": "2026-04-01", "monthlyAmountAED": 2350,
                    "monthsSuspended": 3},
        "phone": "+971-50-XXX-4821",
    },
    "784-1990-1122334-2": {
        "emiratesId": "784-1990-1122334-2",
        "nameEn": "Ahmed Al Suwaidi", "nameAr": "أحمد السويدي",
        "nationality": "UAE", "emirate": "Ajman", "familySize": 6,
        "employment": {"status": "Employed", "employer": "Gulf Logistics FZE",
                       "declaredMonthlyIncomeAED": 27000,
                       "incomeVerifiedUntil": "2027-01-31"},
        "benefit": {"program": "Inflation Allowance", "status": "REJECTED",
                    "statusReason": "INCOME_ABOVE_THRESHOLD",
                    "suspendedSince": None, "monthlyAmountAED": 0,
                    "monthsSuspended": 0},
        "phone": "+971-55-XXX-7710",
    },
}


def lookup(emirates_id: str) -> dict | None:
    return CITIZENS.get(emirates_id.strip())
