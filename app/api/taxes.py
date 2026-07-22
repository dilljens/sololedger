"""Tax routes."""
import datetime
from decimal import Decimal
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..ledger import Ledger
from .deps import _err, _ok, check_auth, get_config

router = APIRouter(prefix="/api/v1")


class TaxPayRequest(BaseModel):
    amount: float
    quarter: str = ""
    year: int = 0
    note: str = "Estimated tax payment"


def _build_tax_estimate_response(annual: dict, quarterly: dict,
                                  ytd_net: Decimal, projection: Decimal,
                                  disclaimer: str) -> dict:
    """Build the tax estimate response, branching on entity_type.

    SMLLC path returns self_employment_tax (unchanged).
    S-Corp path returns fica + form_1120s instead.
    """
    entity_type = annual.get("entity_type", "smllc")
    is_scorp = entity_type == "scorp"

    base = {
        "entity_type": entity_type,
        "ytd_net_profit": float(ytd_net),
        "projected_annual_net": float(projection),
        "total_estimated_tax": float(annual["total_tax"]),
        "effective_tax_rate": annual["effective_tax_rate"],
        "already_paid": float(quarterly["already_paid"]),
        "suggested_next_payment": float(quarterly["suggested_payment"]),
        "remaining_quarters": quarterly["remaining_quarters"],
        "note": quarterly["note"],
        "disclaimer": disclaimer,
    }

    if is_scorp:
        fica = annual.get("fica", {})
        form1120 = annual.get("form_1120s", {})
        base["federal_income_tax"] = {
            "total": float(annual["federal_income_tax"]["income_tax"]),
            "taxable_income": float(annual["federal_income_tax"]["taxable_income"]),
            "effective_rate": annual["federal_income_tax"]["effective_rate"],
        }
        base["fica"] = {
            "salary": float(fica.get("salary", 0)),
            "employee_total": float(fica.get("employee", {}).get("total", 0)),
            "employer_total": float(fica.get("employer", {}).get("total", 0)),
            "total_fica": float(fica.get("total_fica", 0)),
        }
        base["form_1120s"] = {
            "ordinary_income": float(form1120.get("ordinary_income", 0)),
            "officer_salary": float(form1120.get("officer_salary", 0)),
            "employer_payroll_taxes": float(form1120.get("employer_payroll_taxes", 0)),
        }
        # Include SE tax as null so callers can check
        base["self_employment_tax"] = None
    else:
        base["self_employment_tax"] = {
            "total": float(annual["self_employment_tax"]["total_se_tax"]),
            "deductible_half": float(annual["self_employment_tax"]["deductible_half"]),
        }
        base["federal_income_tax"] = {
            "total": float(annual["federal_income_tax"]["income_tax"]),
            "taxable_income": float(annual["federal_income_tax"]["taxable_income"]),
            "effective_rate": annual["federal_income_tax"]["effective_rate"],
        }

    return base


@router.get("/tax/estimate", dependencies=[Depends(check_auth)])
async def tax_estimate(projected_income: Optional[float] = Query(None)):
    try:
        cfg = get_config()
        ledger = Ledger(cfg)
        from ..taxes import TaxEstimator as TE
        taxer = TE(cfg, ledger)
    except Exception as e:
        return _err(f"Tax engine error: {e}", 500)

    ytd_net = ledger.net_income()

    if projected_income:
        projection = Decimal(str(projected_income))
    else:
        projection = ytd_net * Decimal("2")

    if ytd_net <= 0:
        return _ok({"note": "No net profit yet. No tax estimated."})

    annual = taxer.total_projected_tax(projection)
    quarterly = taxer.quarterly_estimate(ytd_net, projection)

    from ..disclaimer import TAX_DISCLAIMER
    return _ok(_build_tax_estimate_response(annual, quarterly, ytd_net, projection, TAX_DISCLAIMER))


@router.get("/tax/deadlines", dependencies=[Depends(check_auth)])
async def tax_deadlines():
    try:
        cfg = get_config()
        ledger = Ledger(cfg)
        from ..taxes import TaxEstimator
        taxer = TaxEstimator(cfg, ledger)
    except Exception as e:
        return _err(f"Tax engine error: {e}", 500)

    info = taxer.deadline_info()
    return _ok(info)


@router.get("/tax/schedule-c", dependencies=[Depends(check_auth)])
async def tax_schedule_c():
    try:
        cfg = get_config()
        ledger = Ledger(cfg)
        from ..taxes import TaxEstimator
        taxer = TaxEstimator(cfg, ledger)
    except Exception as e:
        return _err(f"Tax engine error: {e}", 500)

    entity_type = getattr(cfg, 'entity_type', 'smllc')
    summary = taxer.schedule_c_summary()
    return _ok({
        "entity_type": entity_type,
        "gross_receipts": float(summary["gross_receipts"]),
        "total_expenses": float(summary["total_expenses"]),
        "net_profit": float(summary["net_profit"]),
        "expense_detail": [
            {"account": e["account"], "amount": float(e["amount"])}
            for e in summary["expense_detail"]
        ],
        "taxes_paid": {
            "federal_estimated": float(summary["taxes_paid"]["federal_estimated"]),
            "fica_employer": float(summary["taxes_paid"]["fica_employer"]),
        },
    })


@router.get("/tax/form-1120s", dependencies=[Depends(check_auth)])
async def tax_form_1120s(projected_income: Optional[float] = Query(None)):
    """Generate Form 1120-S data for S-Corp tax filing."""
    try:
        cfg = get_config()
        ledger = Ledger(cfg)
        from ..taxes import TaxEstimator
        taxer = TaxEstimator(cfg, ledger)
    except Exception as e:
        return _err(f"Tax engine error: {e}", 500)

    entity_type = getattr(cfg, 'entity_type', 'smllc')
    if entity_type != "scorp":
        return _err("Form 1120-S is for S-Corp (entity_type='scorp'). Use /tax/schedule-c for SMLLC.", 400)

    ytd_net = ledger.net_income()
    if projected_income:
        projection = Decimal(str(projected_income))
    else:
        projection = ytd_net * Decimal("2")

    ytd_revenue = ledger.gross_revenue()
    projected_revenue = ytd_revenue * Decimal("2") if ytd_revenue > 0 else projection * Decimal("1.1")

    result = taxer.form_1120s_export(projection, total_revenue=projected_revenue)

    income = result["income"]
    bs = result["balance_sheet"]
    shareholder = result["shareholder"]

    def d(v):
        return float(v) if isinstance(v, Decimal) else v

    return _ok({
        "form": "1120-S",
        "shareholder_name": shareholder["name"],
        "ownership_pct": shareholder["ownership_pct"],
        "income": {
            "gross_receipts": d(income["gross_receipts"]),
            "officer_compensation": d(income["officer_compensation"]),
            "employer_payroll_taxes": d(income["employer_payroll_taxes"]),
            "other_deductions": d(income["other_deductions"]),
            "ordinary_income": d(income["ordinary_income"]),
        },
        "balance_sheet": {
            "cash": d(bs["cash"]),
            "accounts_receivable": d(bs["accounts_receivable"]),
            "total_assets": d(bs["total_assets"]),
        },
        "k1_ordinary_income": d(shareholder["ordinary_income"]),
    })


@router.get("/tax/voucher", dependencies=[Depends(check_auth)])
async def tax_voucher(quarter: str = Query("Q3"), amount: Optional[float] = Query(None)):
    if quarter not in ("Q1", "Q2", "Q3", "Q4"):
        raise HTTPException(status_code=400, detail="Quarter must be Q1, Q2, Q3, or Q4")

    cfg = get_config()
    ledger = Ledger(cfg)

    if amount is None:
        from ..taxes import TaxEstimator
        taxer = TaxEstimator(cfg, ledger, state_code=cfg.state_code)
        net = ledger.net_income()
        if net > 0:
            est = taxer.quarterly_estimate(net)
            amount = float(est["suggested_payment"])
        else:
            amount = 0.0

    from jinja2 import Environment, FileSystemLoader, select_autoescape

    env = Environment(loader=FileSystemLoader(str(cfg.project_root / "templates")),
                      autoescape=select_autoescape(['html', 'xml']))
    template = env.get_template("voucher.html")

    html = template.render(
        business=cfg,
        quarter=quarter,
        year=str(datetime.date.today().year),
        amount=amount,
        today=datetime.date.today().isoformat(),
    )

    pdf_dir = cfg.output_dir / "vouchers"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = pdf_dir / f"1040-ES-{quarter}-{datetime.date.today().year}.pdf"

    try:
        from weasyprint import HTML
        HTML(string=html).write_pdf(str(pdf_path))
    except ImportError:
        pdf_path = pdf_path.with_suffix(".html")
        pdf_path.write_text(html)

    from fastapi.responses import FileResponse
    return FileResponse(str(pdf_path), media_type="application/pdf" if pdf_path.suffix == ".pdf" else "text/html",
                        filename=pdf_path.name)


@router.post("/tax/pay", dependencies=[Depends(check_auth)])
async def tax_pay(req: TaxPayRequest):
    from decimal import Decimal

    cfg = get_config()
    ledger = Ledger(cfg)

    amt = Decimal(str(req.amount)).quantize(Decimal("0.01"))
    quarter_str = f" {req.quarter}" if req.quarter else ""
    year_str = f" {req.year}" if req.year else f" {datetime.date.today().year}"

    narration = f"Estimated tax payment{quarter_str}{year_str}"
    if req.note and req.note != "Estimated tax payment":
        narration = req.note

    postings = [
        ("Expenses:Taxes:Federal", f"{amt:.2f} USD"),
        (cfg.checking_account, f"-{amt:.2f} USD"),
    ]

    ledger.append(
        date=datetime.date.today(),
        payee="IRS",
        narration=narration,
        postings=postings,
    )

    ledger.reload(force=True)
    net = ledger.net_income()
    from ..taxes import TaxEstimator
    taxer = TaxEstimator(cfg, ledger, state_code=cfg.state_code)
    est = taxer.quarterly_estimate(net) if net > 0 else {}

    return _ok({
        "recorded": True,
        "amount": float(amt),
        "narration": narration,
        "already_paid": float(est.get("already_paid", 0)) if est else 0,
        "remaining": float(est.get("remaining", 0)) if est else 0,
        "suggested_next": float(est.get("suggested_payment", 0)) if est else 0,
    })
