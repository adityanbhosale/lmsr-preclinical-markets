"""Unit tests for Event and EventQueue."""
from __future__ import annotations

import pytest

from sim.events import Event, EventQueue, EventPriority


class TestEventOrdering:
    def test_lower_timestamp_first(self):
        a = Event(timestamp=10, priority=0, insertion_order=0, event_type="a")
        b = Event(timestamp=5, priority=0, insertion_order=1, event_type="b")
        assert b < a

    def test_same_timestamp_lower_priority_first(self):
        a = Event(timestamp=10, priority=10, insertion_order=0, event_type="a")
        b = Event(timestamp=10, priority=5, insertion_order=1, event_type="b")
        assert b < a

    def test_insertion_order_breaks_ties(self):
        a = Event(timestamp=10, priority=5, insertion_order=2, event_type="a")
        b = Event(timestamp=10, priority=5, insertion_order=1, event_type="b")
        assert b < a

    def test_total_ordering_at_pop(self):
        """No ambiguity: every pair of events at same (t, prio) has a defined order."""
        q = EventQueue()
        q.push(timestamp=10, event_type="a", priority=5)
        q.push(timestamp=10, event_type="b", priority=5)
        q.push(timestamp=10, event_type="c", priority=5)
        assert q.pop().event_type == "a"
        assert q.pop().event_type == "b"
        assert q.pop().event_type == "c"


class TestEventQueueBasics:
    def test_push_pop_single(self):
        q = EventQueue()
        q.push(timestamp=5, event_type="x", payload={"v": 1})
        e = q.pop()
        assert e.timestamp == 5
        assert e.event_type == "x"
        assert e.payload == {"v": 1}

    def test_peek_does_not_remove(self):
        q = EventQueue()
        q.push(timestamp=1, event_type="x")
        assert q.peek().event_type == "x"
        assert len(q) == 1
        assert q.pop().event_type == "x"

    def test_pop_empty_raises(self):
        q = EventQueue()
        with pytest.raises(IndexError):
            q.pop()

    def test_peek_empty_returns_none(self):
        q = EventQueue()
        assert q.peek() is None

    def test_bool_and_len(self):
        q = EventQueue()
        assert not q
        assert len(q) == 0
        q.push(timestamp=1, event_type="x")
        assert q
        assert len(q) == 1

    def test_rejects_non_integer_timestamp(self):
        q = EventQueue()
        with pytest.raises(TypeError):
            q.push(timestamp=1.5, event_type="x")
        with pytest.raises(TypeError):
            q.push(timestamp=True, event_type="x")  # bool is subclass of int — reject

    def test_pop_order_mixed(self):
        q = EventQueue()
        q.push(timestamp=10, event_type="d", priority=0)
        q.push(timestamp=5, event_type="a", priority=0)
        q.push(timestamp=5, event_type="b", priority=10)
        q.push(timestamp=7, event_type="c", priority=0)
        assert [q.pop().event_type for _ in range(4)] == ["a", "b", "c", "d"]

    def test_total_pushed_counter(self):
        q = EventQueue()
        assert q.total_pushed == 0
        for i in range(5):
            q.push(timestamp=i, event_type="x")
        assert q.total_pushed == 5
        q.pop()
        # Counter tracks pushes, not current size
        assert q.total_pushed == 5
        assert len(q) == 4
