# *******************************************************************************
# © Copyright sasadangelo 2026
# ******************************************************************************/
"""
Compare the household's ordinary spending (one-off expenses excluded) with the ISTAT averages.

Public data: references/istat-2025.json (ISTAT averages, shipped with the skill).
Private profile: data/benchmark.json, for example:

    {
      "household": "Coppia con 2 figli",
      "threshold_percent": 10,
      "excluded_categories": ["Mortgage and loans"],
      "excluded_istat": ["Affitti figurativi"],
      "groups": [
        {"label": "Abbigliamento", "categories": ["Abbigliamento e accessori"],
         "istat": ["Abbigliamento e calzature"]},
        {"label": "Hi-tech e telefono", "categories": ["Hi-tech e informatica", "Utenze / Telefono"],
         "istat": ["Informazione e comunicazione"]}
      ]
    }

ISTAT does not publish the expense divisions by household type, so each division is scaled by
household total / Italy total (e.g. couple with 2 children: 3.618 / 2.782 = 1,30). A category is written as
"Category" or "Category / Subcategory". Categories not listed in any group are not compared one by one but
still count in the overall gap.

The overall recurring gap compares all ordinary spending (minus excluded_categories, e.g. loan installments, which
ISTAT does not count as consumption) with the household total minus excluded_istat (e.g. imputed rent for home
owners; subtracted unscaled, since housing scales much less than proportionally with household size).
"""

import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

ISTAT_FILE = Path(__file__).resolve().parent.parent / "references" / "istat-2025.json"
PROFILE_FILE = "benchmark.json"


@dataclass
class Comparison:
    """Ordinary spending of one group of categories against the ISTAT estimate."""

    label: str
    spent: Decimal
    benchmark: Decimal

    @property
    def difference(self) -> Decimal:
        """Euro above (positive) or below (negative) the benchmark."""
        return self.spent - self.benchmark

    @property
    def percent(self) -> Decimal:
        """Difference as a percentage of the benchmark."""
        return self.difference / self.benchmark * 100


@dataclass
class BenchmarkProfile:
    """The user's comparison settings."""

    household: str
    threshold_percent: Decimal
    groups: list[dict[str, object]]
    istat: dict[str, object]
    excluded_categories: list[str]
    excluded_istat: list[str]

    @classmethod
    def load(cls, data_dir: Path) -> "BenchmarkProfile | None":
        """Load data/benchmark.json; None when the user has not configured a comparison."""
        path = data_dir / PROFILE_FILE
        if not path.exists():
            return None
        profile = json.loads(path.read_text(encoding="utf-8"))
        istat = json.loads(ISTAT_FILE.read_text(encoding="utf-8"))
        if profile["household"] not in istat["households"]:
            raise ValueError(f"Unknown ISTAT household type {profile['household']!r} in {path}")
        return cls(
            household=profile["household"],
            threshold_percent=Decimal(str(profile.get("threshold_percent", 20))),
            groups=profile["groups"],
            istat=istat,
            excluded_categories=profile.get("excluded_categories", []),
            excluded_istat=profile.get("excluded_istat", []),
        )

    @property
    def scale(self) -> Decimal:
        """Household total spending relative to the Italian average household."""
        households: dict[str, float] = self.istat["households"]  # type: ignore[assignment]
        return Decimal(str(households[self.household])) / Decimal(str(self.istat["italy_total"]))

    def compare(self, spent_by_category: dict[str, Decimal]) -> list[Comparison]:
        """
        Compare each configured group.

        Args:
            spent_by_category: Positive ordinary spending keyed by "Category" and "Category / Subcategory"

        Returns:
            One comparison per group, most over-budget first
        """
        divisions: dict[str, float] = self.istat["divisions"]  # type: ignore[assignment]
        result = []
        for group in self.groups:
            names: list[str] = group["categories"]  # type: ignore[assignment]
            istat_names: list[str] = group["istat"]  # type: ignore[assignment]
            spent = sum((spent_by_category.get(n, Decimal(0)) for n in names), Decimal(0))
            base = sum((Decimal(str(divisions[d])) for d in istat_names), Decimal(0))
            result.append(Comparison(str(group.get("label") or " + ".join(names)), spent, base * self.scale))
        return sorted(result, key=lambda c: -c.percent)

    def over_threshold(self, spent_by_category: dict[str, Decimal]) -> list[Comparison]:
        """Only the groups whose spending exceeds the benchmark by more than the threshold."""
        return [c for c in self.compare(spent_by_category) if c.percent > self.threshold_percent]


@dataclass
class RecurringGap:
    """How far the recurring (ordinary) spending is from the ISTAT benchmark, broken down so that it adds up."""

    over_threshold: list[Comparison]
    over_below_threshold: list[Comparison]
    under: list[Comparison]
    spent: Decimal
    benchmark: Decimal

    @property
    def total(self) -> Decimal:
        """Overall gap: positive = over budget."""
        return self.spent - self.benchmark

    @property
    def not_comparable(self) -> Decimal:
        """Part of the gap from categories not compared one by one (cash, utilities, mixed items)."""
        explained = sum(
            (c.difference for c in self.over_threshold + self.over_below_threshold + self.under), Decimal(0)
        )
        return self.total - explained


def recurring_gap(
    profile: BenchmarkProfile, spent_by_category: dict[str, Decimal], total_ordinary: Decimal
) -> RecurringGap:
    """
    Break down the gap between ordinary spending and the ISTAT household benchmark.

    Args:
        profile: The user's comparison profile
        spent_by_category: Positive ordinary spending keyed by "Category" and "Category / Subcategory"
        total_ordinary: All ordinary spending of the month (one-offs excluded), positive

    Returns:
        The breakdown: categories over the threshold, over but below the threshold, under the benchmark, remainder
    """
    comparisons = profile.compare(spent_by_category)
    households: dict[str, float] = profile.istat["households"]  # type: ignore[assignment]
    divisions: dict[str, float] = profile.istat["divisions"]  # type: ignore[assignment]
    excluded_spent = sum((spent_by_category.get(c, Decimal(0)) for c in profile.excluded_categories), Decimal(0))
    excluded_istat = sum((Decimal(str(divisions[d])) for d in profile.excluded_istat), Decimal(0))
    return RecurringGap(
        over_threshold=sorted(
            (c for c in comparisons if c.percent > profile.threshold_percent), key=lambda c: -c.difference
        ),
        over_below_threshold=[c for c in comparisons if 0 < c.percent <= profile.threshold_percent],
        under=[c for c in comparisons if c.percent <= 0],
        spent=total_ordinary - excluded_spent,
        benchmark=Decimal(str(households[profile.household])) - excluded_istat,
    )
