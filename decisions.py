"""Fixed, directed disorder on a periodic social ring."""

from dataclasses import dataclass
from math import fsum, isfinite
from random import Random
from typing import Iterable, Sequence


@dataclass(frozen=True)
class Disorder:
    mu_mean: float
    mu_sd: float
    phi_mean: float
    phi_sd: float
    sigma_j: float
    seed: int

    def __post_init__(self):
        values = (self.mu_mean, self.mu_sd, self.phi_mean, self.phi_sd, self.sigma_j)
        if not all(map(isfinite, values)) or min(self.mu_sd, self.phi_sd, self.sigma_j) < 0:
            raise ValueError("invalid disorder parameters")


@dataclass(frozen=True)
class Link:
    target: int
    weight: float
    xi: float
    j: float


def ring_kernel(size: int, radius: int, sigma: float):
    if not 1 <= radius < size / 2 or not isfinite(sigma):
        raise ValueError("require 1 <= radius < size/2 and finite sigma")
    weights = [r ** (-(1 + sigma)) for r in range(1, radius + 1)]
    norm = 2 * fsum(weights)
    return tuple(
        tuple(((i + side * r) % size, weight / norm)
              for r, weight in enumerate(weights, 1) for side in (-1, 1))
        for i in range(size)
    )


@dataclass(frozen=True)
class SocialRing:
    ids: tuple[str, ...]
    radius: int
    sigma: float
    mu: tuple[float, ...]
    phi: tuple[float, ...]
    links: tuple[tuple[Link, ...], ...]
    sigma_j: float
    disorder: Disorder | None = None

    @classmethod
    def from_values(cls, ids, radius, sigma, mu, phi, xi, sigma_j):
        """xi rows follow distance order, with left then right at each distance."""
        ids, mu, phi = tuple(ids), tuple(mu), tuple(phi)
        kernel = ring_kernel(len(ids), radius, sigma)
        return cls._assemble(ids, radius, sigma, mu, phi, xi, sigma_j, kernel)

    @classmethod
    def sample(cls, ids, radius, sigma, disorder):
        ids = tuple(ids)
        kernel = ring_kernel(len(ids), radius, sigma)
        rng = Random(disorder.seed)
        mu = tuple(rng.gauss(disorder.mu_mean, disorder.mu_sd) for _ in ids)
        phi = tuple(rng.gauss(disorder.phi_mean, disorder.phi_sd) for _ in ids)
        xi = [tuple(rng.gauss(0, 1) for _ in row) for row in kernel]
        return cls._assemble(ids, radius, sigma, mu, phi, xi, disorder.sigma_j, kernel, disorder)

    @classmethod
    def _assemble(cls, ids, radius, sigma, mu, phi, xi, sigma_j, kernel, disorder=None):
        if len(set(ids)) != len(ids) or not len(ids) == len(mu) == len(phi) == len(xi):
            raise ValueError("one row of disorder per unique ID")
        if any(len(row) != 2 * radius for row in xi):
            raise ValueError("provide xi for every directed reference")
        if sigma_j < 0 or not all(map(isfinite, (*mu, *phi, sigma_j, *(x for row in xi for x in row)))):
            raise ValueError("invalid realized disorder")
        links = tuple(
            tuple(Link(target, weight, x, offset + sigma_j * x)
                  for (target, weight), x in zip(neighbors, noise))
            for neighbors, noise, offset in zip(kernel, xi, mu)
        )
        return cls(ids, radius, sigma, mu, phi, links, sigma_j, disorder)

    def validate_state(self, state):
        if len(state) != len(self.ids) or any(type(s) is not int or s not in (-1, 1) for s in state):
            raise ValueError("provide one binary intention per fixed ID")

    def update(self, old: Sequence[int], h: float) -> tuple[int, ...]:
        self.validate_state(old)
        if not isfinite(h):
            raise ValueError("field must be finite")
        fields = (
            fsum([h, -phi, *(link.weight * link.j * old[link.target] for link in row)])
            for phi, row in zip(self.phi, self.links)
        )
        return tuple(1 if field > 0 else -1 if field < 0 else s for field, s in zip(fields, old))

    def evolve(self, initial: Sequence[int], fields: Iterable[float]):
        """Yield the initial state followed by synchronous decision updates."""
        state = tuple(initial)
        self.validate_state(state)
        yield state
        for h in fields:
            state = self.update(state, h)
            yield state
