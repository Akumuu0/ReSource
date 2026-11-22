"""AI feature 2: matching and ranking (design Section 17, Fig. 9-4 RankingModel).

The SCORE is a weighted sum of eight factors that anyone can check by hand (design Table 17-1):
    score = round(100 x (w1 F1 + w2 F2 + ... + w8 F8))     every factor between 0 and 1
The CONFIDENCE comes from the score with the design's logistic curve (Section 17.2).
The STRENGTHS and the MAIN LIMITATION come from the weighted factors (Section 17.3).
The language model only writes the "in plain words" sentence for each of the top 5.
The requester then selects the top match, chooses another one with a reason, or rejects all (H-2).
"""
import json
import math
import re
from datetime import date

from assets.models import Asset
from sustainability.models import CategoryValue

from .gateway import AIGateway
from .models import FACTOR_LABELS, AIOutput, Recommendation
from .text_tools import words

RULES_VERSION = "rank rules v3"

# Rule set v3 (design Table 17-1). The weights add up to 1.0.
WEIGHTS = {
    "function": 0.35,   # F1 function and specifications
    "quantity": 0.15,   # F2 enough free units
    "condition": 0.10,  # F3 current condition, and the minimum asked for
    "location": 0.10,   # F4 same campus or other campus
    "ready": 0.10,      # F5 free by the date needed
    "repair": 0.08,     # F6 expected repair cost
    "transfer": 0.07,   # F7 cost of moving it
    "carbon": 0.05,     # F8 waste and carbon saved
}
# How each factor is calculated, as shown under "How the score works".
FORMULAS = {
    "function": "share of your words (purpose and specifications) found in the asset text, "
                "halved for each specification it does not meet",
    "quantity": "free units ÷ units needed (at most 1)",
    "condition": "New 1.0, Good 0.9, Fair 0.6, Poor 0.3; at most 0.3 if below your minimum",
    "location": "same campus 0.85, other campus 0.55 (your own department's assets are not candidates)",
    "ready": "1.0 if free by your date, 0.5 if up to 2 days late, otherwise 0",
    "repair": "1 − repair cost ÷ replacement value (at least 0)",
    "transfer": "1 − moving cost ÷ (0.15 × replacement value) (at least 0)",
    "carbon": "kg CO2e saved ÷ the largest kg CO2e among the candidates (0 if the category has no emission factor)",
}

CONDITION_ORDER = ["Poor", "Fair", "Good", "New"]
CONDITION_SCORES = {"New": 1.0, "Good": 0.9, "Fair": 0.6, "Poor": 0.3}
LOCATION_SCORES = {"same campus": 0.85, "other campus": 0.55}
MOVING_COSTS = {"same campus": 40, "other campus": 120}  # AED, sample values of design Table 17-3
WHERE = {"same campus": "on your campus", "other campus": "on another campus"}
URGENCY_MULTIPLIERS = {"Low": 0.5, "Medium": 1.0, "High": 2.0}  # applied to the F5 weight
PLATT_A, PLATT_B = 4.60, -2.57  # confidence curve, the design's example fit (Section 17.2)
TOP_N = 5
WEAK_SCORE = 60  # below this for every candidate: show a "weak matches" warning (Section 17.1)

# A number with its unit: "70 MHz", "2 channels", "24-inch".
SPEC = re.compile(r"(\d+(?:\.\d+)?)\s*-?\s*([a-z]+)", re.IGNORECASE)

SYSTEM_PROMPT = (
    "You explain matches in a campus reuse system. The candidates are already scored by fixed rules. "
    "For each candidate write ONE plain sentence (at most 25 words) with its main strength and its main limitation. "
    "Use only the facts given. Do not invent facts or numbers."
)


def specs_in(text):
    """Number-and-unit pairs: "At least 70 MHz" gives [(70.0, "mhz", "70 MHz")]."""
    pairs = []
    for match in SPEC.finditer(text):
        unit = match.group(2).lower()
        if len(unit) > 3 and unit.endswith("s"):
            unit = unit[:-1]  # "channels" -> "channel"
        pairs.append((float(match.group(1)), unit, match.group(0)))
    return pairs


def cost_factor(cost, limit):
    """1 - cost / limit, between 0 and 1 (used by F6 and F7)."""
    if cost == 0:
        return 1.0
    if limit <= 0:
        return 0.0
    return max(0.0, 1 - cost / limit)


class RankingModel:

    @staticmethod
    def weights_for(req):
        """Urgency changes the F5 weight; then all weights are rescaled to add up to 1 (Section 17.1)."""
        weights = dict(WEIGHTS)
        weights["ready"] *= URGENCY_MULTIPLIERS[req.urgency]
        total = sum(weights.values())
        return {name: weight / total for name, weight in weights.items()}

    @staticmethod
    def asset_words(asset):
        return words(f"{asset.name} {asset.description} {asset.tags} {asset.category.name}")

    @staticmethod
    def candidates(req):
        """Published assets of OTHER departments with free units, in the requested category or sharing a word
        with the need. Assets of the requester's own department are left out: moving them changes nothing."""
        wanted = words(f"{req.purpose} {req.specifications}")
        published = Asset.objects.filter(state=Asset.AVAILABLE, available_quantity__gt=0).exclude(
            department_id=req.department_id).select_related("category", "department")
        return [asset for asset in published
                if asset.category_id == req.category_id or wanted & RankingModel.asset_words(asset)]

    @staticmethod
    def distance(req, asset):
        return "same campus" if asset.department.campus == req.department.campus else "other campus"

    @staticmethod
    def unmet_specs(req, asset):
        """Specifications are minimums ("at least 70 MHz"). One is unmet when the asset states a lower value."""
        offered = specs_in(f"{asset.name} {asset.description} {asset.tags}")
        unmet = []
        for value, unit, text in specs_in(req.specifications):
            values = [number for number, offered_unit, _ in offered if offered_unit == unit]
            if values and max(values) < value:
                unmet.append(text)
        return unmet

    @staticmethod
    def below_minimum(req, asset):
        return bool(req.min_condition) and (
            CONDITION_ORDER.index(asset.condition) < CONDITION_ORDER.index(req.min_condition))

    @staticmethod
    def carbon(req, asset):
        """kg CO2e saved if the units are reused instead of bought new (design Section 18)."""
        factor = CategoryValue.emission_factor(asset.category)
        if factor is None:
            return 0.0  # the category has no emission factor (FR-13.8)
        units = min(asset.available_quantity, req.quantity)
        return float(units * asset.weight_kg * factor)

    @staticmethod
    def factors(req, asset, largest_carbon):
        """The eight factor values, each between 0 and 1, rounded to 2 decimals (design Table 17-1)."""
        wanted = words(f"{req.purpose} {req.specifications}")
        share = len(wanted & RankingModel.asset_words(asset)) / len(wanted) if wanted else 0.0
        condition = CONDITION_SCORES[asset.condition]
        if RankingModel.below_minimum(req, asset):
            condition = min(condition, 0.3)
        days_late = (date.today() - req.needed_by).days  # every candidate is free now
        distance = RankingModel.distance(req, asset)
        price = float(asset.estimated_value)
        values = {
            "function": share * 0.5 ** len(RankingModel.unmet_specs(req, asset)),
            "quantity": min(asset.available_quantity, req.quantity) / req.quantity,
            "condition": condition,
            "location": LOCATION_SCORES[distance],
            "ready": 1.0 if days_late <= 0 else 0.5 if days_late <= 2 else 0.0,
            "repair": cost_factor(float(asset.repair_cost), price),
            "transfer": cost_factor(MOVING_COSTS[distance], 0.15 * price),
            "carbon": RankingModel.carbon(req, asset) / largest_carbon if largest_carbon else 0.0,
        }
        return {name: round(value, 2) for name, value in values.items()}

    @staticmethod
    def score(factors, weights=WEIGHTS):
        return round(100 * sum(weights[name] * factors[name] for name in weights))

    @staticmethod
    def confidence(score):
        """How likely the requester finds this candidate suitable: 1 / (1 + e^-(a x S + b)), S = score / 100."""
        return round(1 / (1 + math.exp(-(PLATT_A * score / 100 + PLATT_B))), 2)

    @staticmethod
    def strengths(factors, weights):
        """The three factors with the largest weighted values (w x F)."""
        best = sorted(weights, key=lambda name: weights[name] * factors[name], reverse=True)[:3]
        return ", ".join(FACTOR_LABELS[name] for name in best)

    @staticmethod
    def limitation(req, asset, factors, weights):
        """The factor with the largest weighted gap, w x (1 - F), in plain words."""
        name = max(weights, key=lambda key: weights[key] * (1 - factors[key]))
        if factors[name] == 1.0:
            return "no real limitation"
        distance = RankingModel.distance(req, asset)
        unmet = RankingModel.unmet_specs(req, asset)
        if name == "function":
            if unmet:
                return f"below your minimum of {', '.join(unmet)}"
            return "does not match what you described" if factors[name] == 0 else "matches only part of your description"
        if name == "quantity":
            return f"only {asset.available_quantity} of the {req.quantity} units you need"
        if name == "condition":
            below = f", below your minimum ({req.min_condition})" if RankingModel.below_minimum(req, asset) else ""
            return f"{asset.condition.lower()} condition{below}"
        if name in ("location", "transfer"):
            return f"{WHERE[distance]}, so moving it costs about AED {MOVING_COSTS[distance]}"
        if name == "ready":
            return "not free by the date you need it"
        if name == "repair":
            return f"needs about AED {asset.repair_cost:,.0f} of repairs per unit"
        return "saves less waste and carbon than other candidates"

    @staticmethod
    def rule_reason(detail):
        """Fallback "in plain words" sentence, built only from the strengths and the limitation."""
        return f"Strong on {detail['strengths'].lower()}. Main limitation: {detail['limitation']}."

    def rank(self, user, req):
        """Score every candidate and save the top 5 as Recommendations. Returns (recommendations, AIOutput)."""
        weights = self.weights_for(req)
        candidates = self.candidates(req)
        largest_carbon = max((self.carbon(req, asset) for asset in candidates), default=0)
        details = []
        for asset in candidates:
            factors = self.factors(req, asset, largest_carbon)
            details.append({"asset": asset, "factors": factors, "score": self.score(factors, weights),
                            "strengths": self.strengths(factors, weights),
                            "limitation": self.limitation(req, asset, factors, weights)})
        details.sort(key=lambda detail: (-detail["score"], detail["asset"].code))
        top = details[:TOP_N]
        if not top:
            return [], None

        schema = {
            "type": "object",
            "properties": {"reasons": {"type": "array", "items": {"type": "string"}}},
            "required": ["reasons"],
            "additionalProperties": False,
        }
        result = AIGateway().run(
            AIOutput.MATCHING, SYSTEM_PROMPT, self.prompt(req, top), schema,
            fallback=lambda: {"reasons": [self.rule_reason(detail) for detail in top]},
            user=user,
            validate=lambda data: "" if len(data["reasons"]) == len(top) and all(data["reasons"])
            else "wrong number of reasons",
            confidence=self.confidence(top[0]["score"]),
        )
        recommendations = []
        for rank, (detail, reason) in enumerate(zip(top, result.data["reasons"]), start=1):
            recommendations.append(Recommendation.objects.create(
                output=result.output, request=req if req.pk else None,  # None for an unsaved need
                asset=detail["asset"], rank=rank, score=detail["score"],
                confidence=self.confidence(detail["score"]), factors=json.dumps(detail["factors"]),
                reason=reason, strengths=detail["strengths"], limitation=detail["limitation"],
            ))
        return recommendations, result.output

    @staticmethod
    def prompt(req, top):
        """Only the text the model needs: no codes, no department names, no people."""
        lines = [
            f"Need: {req.quantity} unit(s) of {req.category}. Purpose: {req.purpose}. "
            f"Specifications: {req.specifications or 'none'}. Minimum condition: {req.min_condition or 'any'}.",
            "Candidates (already scored by fixed rules):",
        ]
        for number, detail in enumerate(top, start=1):
            asset = detail["asset"]
            lines.append(
                f"{number}. {asset.name}: {asset.description[:150]} | {asset.condition} condition, "
                f"{asset.available_quantity} free unit(s) | score {detail['score']} | "
                f"strengths: {detail['strengths']} | main limitation: {detail['limitation']}"
            )
        lines.append("Write one sentence per candidate, in the same order.")
        return "\n".join(lines)
