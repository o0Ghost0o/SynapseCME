import pytest

from app.graph.states import (
    RANK,
    State,
    Vote,
    agree,
    consensus,
    merge_votes,
    parse_state,
    promote,
    state_transition,
)


def v(conf, who="ana", value="siemens"):
    return Vote(value=value, confidence=conf, contributor=who)


class TestConsensus:
    def test_no_votes_is_desconocido(self):
        assert consensus([]) == (State.DESCONOCIDO, None, 0.0)

    def test_weak_vote_is_estimado(self):
        state, value, weight = consensus([v(0.5)])
        assert state == State.ESTIMADO
        assert value == "siemens"
        assert weight == 0.5

    def test_strong_single_vote_is_reportado(self):
        state, _, weight = consensus([v(1.0)])
        assert state == State.REPORTADO
        assert weight == 1.0

    def test_two_contributors_confirm(self):
        votes = [v(0.6, "ana"), v(0.6, "luis")]
        state, value, _ = consensus(votes)
        assert state == State.CONFIRMADO
        assert value == "siemens"

    def test_majority_wins(self):
        votes = [v(1.0, "ana", "siemens"), v(1.0, "luis", "siemens"), v(1.0, "pepe", "ge")]
        state, value, _ = consensus(votes)
        assert state == State.CONFIRMADO
        assert value == "siemens"

    def test_split_votes_never_confirm(self):
        votes = [v(1.0, "ana", "siemens"), v(1.0, "luis", "ge")]
        state, value, _ = consensus(votes)
        # winning weight is 1.0 but only one contributor backs it
        assert state == State.REPORTADO
        assert value in {"siemens", "ge"}


class TestPromote:
    def test_never_demotes(self):
        current, _ = promote(State.CONFIRMADO, [v(0.3, "nuevo")])
        assert current == State.CONFIRMADO

    def test_promotes_up(self):
        current, _ = promote(State.ESTIMADO, [v(1.0, "ana"), v(0.9, "luis")])
        assert current == State.CONFIRMADO


class TestHelpers:
    def test_state_transition_string(self):
        assert state_transition(State.ESTIMADO, State.REPORTADO) == "Estimado -> Reportado"
        assert state_transition(State.REPORTADO, State.REPORTADO) is None

    def test_parse_state_case_insensitive(self):
        assert parse_state("confirmado") == State.CONFIRMADO
        assert parse_state(None) == State.DESCONOCIDO
        assert parse_state("bogus") == State.DESCONOCIDO

    def test_ordering(self):
        assert RANK[State.DESCONOCIDO] < RANK[State.ESTIMADO] < RANK[State.REPORTADO] < RANK[State.CONFIRMADO]

    def test_agree(self):
        assert agree(v(0.5), Vote(value="Siemens", confidence=0.52, contributor="x"))
        assert not agree(v(0.5, value="ge"), v(0.5, value="siemens"))

    def test_vote_confidence_clamped(self):
        assert v(5.0).confidence == 1.0
        assert v(-1.0).confidence == 0.0

    def test_merge_votes_dedupes_contributor(self):
        votes = merge_votes([v(0.4), v(0.9), v(0.5, who="luis")])
        assert len(votes) == 2
        ana = next(x for x in votes if x.contributor == "ana")
        assert ana.confidence == 0.9
