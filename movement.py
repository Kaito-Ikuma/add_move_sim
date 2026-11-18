"""Synchronous one-cell movement with fixed participant IDs."""

from collections import Counter
from dataclasses import dataclass
from typing import Literal, Sequence


Boundary = Literal["periodic", "absorbing"]
Reason = Literal["intention_stop", "exclusion_stop", "move", "outside"]
REASONS = ("intention_stop", "exclusion_stop", "move")


@dataclass(frozen=True)
class Person:
    id: str
    position: int
    active: bool = True


@dataclass(frozen=True)
class Attempt:
    id: str
    s: int
    active_before: bool
    active_after: bool
    old_position: int | None
    new_position: int | None
    reason: Reason
    exited: bool = False


@dataclass(frozen=True)
class Step:
    people: tuple[Person, ...]
    attempts: tuple[Attempt, ...]

    @property
    def counts(self) -> dict[str, int]:
        counts = Counter(attempt.reason for attempt in self.attempts)
        return {reason: counts[reason] for reason in REASONS}


@dataclass(frozen=True)
class Corridor:
    length: int
    boundary: Boundary

    def __post_init__(self) -> None:
        if type(self.length) is not int or self.length < 1:
            raise ValueError("length must be a positive integer")
        if self.boundary not in ("periodic", "absorbing"):
            raise ValueError("unknown boundary")

    def step(self, people: Sequence[Person], intentions: Sequence[int]) -> Step:
        """Use intentions in fixed roster order, including people who have exited."""
        if len(people) != len(intentions):
            raise ValueError("provide one intention per fixed ID")
        if any(type(s) is not int or s not in (-1, 1) for s in intentions):
            raise ValueError("intentions must be integers +1 or -1")
        if len({person.id for person in people}) != len(people):
            raise ValueError("IDs must be unique")

        positions = [person.position for person in people if person.active]
        if any(type(pos) is not int or not 1 <= pos <= self.length for pos in positions):
            raise ValueError("active positions must be cells 1 through length")
        occupied = set(positions)
        if len(occupied) != len(positions):
            raise ValueError("active positions must be unique")

        updated = []
        attempts = []
        for person, s in zip(people, intentions):
            if not person.active:
                updated.append(person)
                attempts.append(Attempt(person.id, s, False, False, None, None, "outside"))
                continue

            old = person.position
            target = old + 1
            if self.boundary == "periodic" and old == self.length:
                target = 1

            new = old
            reason: Reason
            if s == -1:
                reason = "intention_stop"
            elif target in occupied:
                reason = "exclusion_stop"
            else:
                reason = "move"
                new = target

            exited = new == self.length + 1
            updated.append(Person(person.id, new, active=not exited))
            attempts.append(Attempt(person.id, s, True, not exited, old, new, reason, exited))

        return Step(tuple(updated), tuple(attempts))
