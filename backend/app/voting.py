"""Pure plurality rule: no majority threshold and no fabricated missing votes."""
from collections import Counter
from collections.abc import Iterable


def plurality(choice_ids: Iterable[str], votes: Iterable[str]) -> tuple[dict[str, int], list[str]]:
    counts = Counter(votes)
    totals = {choice: counts[choice] for choice in choice_ids}
    highest = max(totals.values(), default=0)
    return totals, [choice for choice, count in totals.items() if highest > 0 and count == highest]
