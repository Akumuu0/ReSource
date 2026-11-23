"""AI feature 5: generated report (design Fig. 9-4 ReportGenerator, Section 10.5).

1. The database calculates the numbers (SustainabilityCalculator, fixed formulas).
2. The AI writes a short summary around those numbers.
3. We check that EVERY number in the summary is one of the calculated numbers.
   If not, the summary is thrown away and a template text is used instead.
4. The Administrator edits the draft and publishes it (human gate H-10).
"""
import re

from django.db import transaction

from accounts.models import User
from accounts.permissions import require_role
from sustainability.models import AIReport, SustainabilityImpact
from sustainability.services import MEASURES, SustainabilityCalculator

from .gateway import AIGateway
from .models import AIOutput

# A number that is not part of a word (so the "2" in "CO2e" is ignored).
NUMBER = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?")
# A date like 01/11/2026, or else a number (used to put check marks on the figures only).
DATE_OR_NUMBER = re.compile(r"\d{1,2}/\d{1,2}/\d{4}|" + NUMBER.pattern)

SYSTEM_PROMPT = (
    "You write short sustainability summaries for a university reuse programme. "
    "Use ONLY the numbers given, written exactly as given. "
    "Do not write any other numbers, dates or percentages."
)


class ReportGenerator:

    def generate(self, user, start, end):
        """Create a draft AIReport for the period, with its frozen figures."""
        require_role(user, User.ADMINISTRATOR)
        totals, rows = SustainabilityCalculator(start, end).calculate()
        shown = SustainabilityCalculator.display(totals)
        period = f"{start:%d/%m/%Y} to {end:%d/%m/%Y}"

        prompt = (
            f"Period: {period}\n"
            f"Items reused: {shown['items_reused']}\n"
            f"Cost avoided: AED {shown['cost_avoided']}\n"
            f"Waste diverted: {shown['waste_kg']} kg\n"
            f"CO2e avoided: {shown['co2e_kg']} kg CO2e\n\n"
            "Write 2 or 3 plain sentences for university management about these results."
        )
        schema = {
            "type": "object",
            "properties": {"summary": {"type": "string"}},
            "required": ["summary"],
            "additionalProperties": False,
        }
        allowed = self.allowed_numbers(totals, shown, start, end)
        result = AIGateway().run(
            AIOutput.REPORT, SYSTEM_PROMPT, prompt, schema,
            fallback=lambda: {"summary": self.template_text(period, shown)},
            user=user,
            validate=lambda data: self.check_numbers(data["summary"], allowed),
        )
        summary = result.data["summary"]

        with transaction.atomic():
            report = AIReport.objects.create(
                period_start=start, period_end=end, draft_text=summary, final_text=summary,
                ai_output=result.output, created_by=user,
            )
            for measure in MEASURES:
                SustainabilityImpact.objects.create(
                    report=report, period=period, indicator=measure["label"],
                    value=totals[measure["key"]], unit=measure["unit"],
                )
        return report

    @staticmethod
    def allowed_numbers(totals, shown, start, end):
        """Numbers the summary may contain: the figures (exact and as displayed) and the period dates."""
        allowed = {float(value) for value in totals.values()}
        allowed |= {float(text.replace(",", "")) for text in shown.values()}
        allowed |= {start.day, start.month, start.year, end.day, end.month, end.year}
        return allowed

    @staticmethod
    def check_numbers(text, allowed):
        """Return "" if every number in the text is allowed, otherwise the problem."""
        for token in NUMBER.findall(text):
            value = float(token.replace(",", ""))
            if not any(abs(value - number) < 0.001 for number in allowed):
                return f"the number {token} is not one of the calculated figures"
        return ""

    @staticmethod
    def template_text(period, shown):
        """Rule-based summary used when the AI is unavailable or fails the number check."""
        return (
            f"From {period}, {shown['items_reused']} items were reused through ReSource instead of being bought new, "
            f"avoiding about AED {shown['cost_avoided']} in purchases. "
            f"This kept {shown['waste_kg']} kg out of the waste stream and avoided an estimated "
            f"{shown['co2e_kg']} kg CO2e."
        )

    @staticmethod
    def mark_numbers(text, report):
        """Split the text into pieces so the page can put a check mark on every figure (design 7.7).

        Dates stay plain text. A number is "checked" when it is one of the report's frozen figures
        or a part of its period dates.
        """
        allowed = {report.period_start.day, report.period_start.month, report.period_start.year,
                   report.period_end.day, report.period_end.month, report.period_end.year}
        for figure in report.figures.all():
            value = float(figure.value)
            allowed |= {value, round(value), round(value, 1)}
        pieces, last = [], 0
        for match in DATE_OR_NUMBER.finditer(text):
            if "/" in match.group():
                continue  # a date: left in the plain text around it
            pieces.append({"text": text[last:match.start()], "number": False})
            value = float(match.group().replace(",", ""))
            pieces.append({"text": match.group(), "number": True, "checked": value in allowed})
            last = match.end()
        pieces.append({"text": text[last:], "number": False})
        return pieces
