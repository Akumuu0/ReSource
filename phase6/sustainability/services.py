"""Sustainability measures (C7) and the request report (C9).

All numbers come from fixed formulas over the database, never from AI
(design Section 18, FR-13.2), so the same data always gives the same numbers.
"""
import csv
import io
from datetime import date
from decimal import Decimal

from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from accounts.common import BusinessRuleError
from accounts.models import User
from accounts.permissions import require_role
from resource_requests.models import Approval, Request, Transfer

from .models import AIReport, CategoryValue

# What the dashboard shows for each measure: its formula and its source.
MEASURES = [
    {
        "key": "items_reused",
        "label": "Items reused",
        "unit": "items",
        "formula": "items reused = sum of units in every transfer with confirmed receipt",
        "source": "ReSource transfer records (Phase 3 indicator 1). Only completed transfers count.",
    },
    {
        "key": "cost_avoided",
        "label": "Cost avoided",
        "unit": "AED",
        "formula": "cost avoided = sum of (units x replacement value per unit)",
        "source": "Replacement value recorded on each asset by its Asset Coordinator (Phase 3 indicator 3, avoided purchases).",
    },
    {
        "key": "waste_kg",
        "label": "Waste diverted",
        "unit": "kg",
        "formula": "waste diverted = sum of (units x weight per unit in kg)",
        "source": "Weight recorded on each asset (Phase 3 indicator 5).",
    },
    {
        "key": "co2e_kg",
        "label": "CO2e avoided",
        "unit": "kg CO2e",
        "formula": "kg CO2e avoided = sum of (kg diverted x the category's emission factor); "
                   "categories without a factor are left out and listed under Missing data (FR-13.8)",
        "source": "EPA WARM version 16 source-reduction factor for mixed electronics, 22.92 kg CO2e per kg "
                  "(design Section 18.2, reference [15]), stored as a CategoryValue for the electronic categories only.",
    },
]


class SustainabilityCalculator:
    """Calculates the four measures for an optional period and receiving department."""

    def __init__(self, start=None, end=None, department=None):
        self.start = start
        self.end = end
        self.department = department

    def reused_transfers(self):
        """Transfers whose receipt was confirmed: only these count as reuse (FR-13.3)."""
        transfers = Transfer.objects.filter(state=Transfer.RECEIVED).select_related(
            "asset__category", "request", "to_department", "from_department")
        if self.start:
            transfers = transfers.filter(received_at__date__gte=self.start)
        if self.end:
            transfers = transfers.filter(received_at__date__lte=self.end)
        if self.department:
            transfers = transfers.filter(to_department=self.department)
        return transfers.order_by("received_at")

    def calculate(self):
        totals = {"items_reused": 0, "cost_avoided": Decimal("0"), "waste_kg": Decimal("0"), "co2e_kg": Decimal("0")}
        rows = []
        for transfer in self.reused_transfers():
            asset = transfer.asset
            cost = transfer.quantity * asset.estimated_value
            kg = transfer.quantity * asset.weight_kg
            factor = CategoryValue.emission_factor(asset.category)
            co2e = kg * factor if factor is not None else None  # no factor: left out of CO2e (FR-13.8)
            totals["items_reused"] += transfer.quantity
            totals["cost_avoided"] += cost
            totals["waste_kg"] += kg
            if co2e is not None:
                totals["co2e_kg"] += co2e
            rows.append({"transfer": transfer, "cost": cost, "kg": kg, "co2e": co2e})
        totals["co2e_kg"] = totals["co2e_kg"].quantize(Decimal("0.01"))
        return totals, rows

    def monthly_items(self, months=6):
        """Items reused in each of the last 6 months, oldest first, for the trend bars (design 7.6)."""
        today = date.today()
        result = []
        for back in range(months - 1, -1, -1):
            year, month = today.year, today.month - back
            if month < 1:
                year, month = year - 1, month + 12
            transfers = Transfer.objects.filter(state=Transfer.RECEIVED, received_at__year=year, received_at__month=month)
            if self.department:
                transfers = transfers.filter(to_department=self.department)
            items = transfers.aggregate(total=Sum("quantity"))["total"] or 0
            result.append({"label": date(year, month, 1).strftime("%b %Y"), "items": items})
        largest = max(row["items"] for row in result) or 1
        for row in result:
            row["percent"] = round(100 * row["items"] / largest)
        return result

    @staticmethod
    def display(totals):
        """The numbers as people read them. The AI summary must use exactly these."""
        return {
            "items_reused": f"{totals['items_reused']}",
            "cost_avoided": f"{totals['cost_avoided']:,.0f}",
            "waste_kg": f"{totals['waste_kg']:,.1f}",
            "co2e_kg": f"{totals['co2e_kg']:,.1f}",
        }


class RequestReportService:
    """C9: a table of requests and their transfers, with filters and CSV export."""

    COLUMNS = ["Code", "Submitted", "Requesting department", "Requested by", "Asset", "Owner department",
               "Quantity", "State", "Release decision", "Approval decision", "Transfer state", "Received", "Reason"]

    @staticmethod
    def requests_for(user, state="", department=None, date_from=None, date_to=None):
        """Administrators see everything; other users see requests of their own department."""
        requests = Request.objects.select_related(
            "requester", "department", "asset__department", "transfer__from_department"
        ).prefetch_related("approvals__decided_by")
        if not user.is_administrator:
            mine = user.department
            requests = requests.filter(Q(department=mine) | Q(asset__department=mine) | Q(transfer__from_department=mine))
        if state:
            requests = requests.filter(state=state)
        if department:
            requests = requests.filter(Q(department=department) | Q(asset__department=department)
                                       | Q(transfer__from_department=department))
        if date_from:
            requests = requests.filter(created_at__date__gte=date_from)
        if date_to:
            requests = requests.filter(created_at__date__lte=date_to)
        return requests.distinct().order_by("-created_at")

    @staticmethod
    def decision(req, step):
        """e.g. "Approved by admin" for the given step, or "" if not decided yet."""
        for approval in req.approvals.all():
            if approval.step == step:
                return f"{approval.decision} by {approval.decided_by.username}"
        return ""

    @staticmethod
    def as_row(req):
        transfer = req.get_transfer()
        return [
            req.code,
            req.created_at.strftime("%d/%m/%Y"),
            req.department.name,
            req.requester.username,
            f"{req.asset.code} {req.asset.name}" if req.asset else "(open need)",
            req.owner_department.name if req.owner_department else "",
            req.quantity,
            req.state,
            RequestReportService.decision(req, Approval.RELEASE),
            RequestReportService.decision(req, Approval.APPROVAL),
            transfer.state if transfer else "",
            transfer.received_at.strftime("%d/%m/%Y") if transfer and transfer.received_at else "",
            req.reason,
        ]

    @staticmethod
    def to_csv(requests):
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(RequestReportService.COLUMNS)
        for req in requests:
            writer.writerow(RequestReportService.as_row(req))
        return buffer.getvalue()


class SummaryService:
    """AI-5: the Administrator reviews the generated summary before anyone else sees it (H-10)."""

    @staticmethod
    @transaction.atomic
    def publish(user, report, final_text):
        require_role(user, User.ADMINISTRATOR)
        if report.state != AIReport.DRAFT:
            raise BusinessRuleError(f"This summary is already {report.state}.")
        final_text = (final_text or "").strip()
        if not final_text:
            raise BusinessRuleError("The summary text cannot be empty.")
        report.final_text = final_text
        report.state = AIReport.PUBLISHED
        report.published_by = user
        report.published_at = timezone.now()
        report.save()
        edited = final_text != report.draft_text.strip()
        report.ai_output.record_decision(user, "Published after edits" if edited else "Published unchanged")

    @staticmethod
    @transaction.atomic
    def discard(user, report):
        require_role(user, User.ADMINISTRATOR)
        if report.state != AIReport.DRAFT:
            raise BusinessRuleError(f"This summary is already {report.state}.")
        report.state = AIReport.DISCARDED
        report.save()
        report.ai_output.record_decision(user, "Discarded")
