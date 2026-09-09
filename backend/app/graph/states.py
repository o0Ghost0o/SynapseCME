"""Equipment/attribute state consensus — pure functions, no DB access.

States per equipment or attribute:
    Desconocido < Estimado < Reportado < Confirmado

Each observation casts a weighted vote (confidence in [0,1]). Consensus
promotes an attribute as independent contributors corroborate it:
  * no votes                       -> Desconocido
  * any vote, weight < 1.0         -> Estimado
  * weight >= 1.0, one contributor -> Reportado
  * weight >= 1.0, >= 2 distinct contributors -> Confirmado
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Sequence


class State(str, Enum):
    DESCONOCIDO = "Desconocido"
    ESTIMADO = "Estimado"
    REPORTADO = "Reportado"
    CONFIRMADO = "Confirmado"


RANK: dict[State, int] = {
    State.DESCONOCIDO: 0,
    State.ESTIMADO: 1,
    State.REPORTADO: 2,
    State.CONFIRMADO: 3,
}


def parse_state(value: str | None) -> State:
    if not value:
        return State.DESCONOCIDO
    for state in State:
        if state.value.lower() == value.lower():
            return state
    return State.DESCONOCIDO


@dataclass(frozen=True)
class Vote:
    """One observation's support for a specific attribute value."""

    value: str
    confidence: float  # 0..1
    contributor: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "confidence", min(max(self.confidence, 0.0), 1.0))


def consensus(votes: Sequence[Vote]) -> tuple[State, str | None, float]:
    """Aggregate votes for one attribute.

    Returns (state, winning_value, weight_of_winning_value). When votes are
    empty the value is None and the state is Desconocido.
    """
    if not votes:
        return State.DESCONOCIDO, None, 0.0

    totals: dict[str, float] = {}
    contributors: dict[str, set[str]] = {}
    for v in votes:
        totals[v.value] = totals.get(v.value, 0.0) + v.confidence
        contributors.setdefault(v.value, set()).add(v.contributor)

    winning_value = max(totals, key=lambda k: totals[k])
    weight = totals[winning_value]
    n_contributors = len(contributors[winning_value])

    if weight >= 1.0 and n_contributors >= 2:
        state = State.CONFIRMADO
    elif weight >= 1.0:
        state = State.REPORTADO
    else:
        state = State.ESTIMADO
    return state, winning_value, weight


def promote(current: State, votes: Sequence[Vote]) -> tuple[State, str | None]:
    """New state after applying fresh votes; states never demote here."""
    new_state, winning_value, _ = consensus(votes)
    if RANK[new_state] < RANK[current]:
        return current, winning_value
    return new_state, winning_value


def state_transition(current: State, new: State) -> str | None:
    """'Estimado -> Reportado' when changed, None otherwise."""
    if current == new:
        return None
    return f"{current.value} -> {new.value}"


def agree(a: Vote, b: Vote, tolerance: float = 0.05) -> bool:
    """Whether two votes support the same value (for duplicate detection)."""
    return a.value.strip().lower() == b.value.strip().lower() and abs(
        a.confidence - b.confidence
    ) <= tolerance


def merge_votes(votes: Iterable[Vote]) -> list[Vote]:
    """Deduplicate votes from the same contributor keeping the max confidence."""
    best: dict[tuple[str, str], Vote] = {}
    for v in votes:
        key = (v.contributor, v.value.strip().lower())
        if key not in best or v.confidence > best[key].confidence:
            best[key] = v
    return list(best.values())
