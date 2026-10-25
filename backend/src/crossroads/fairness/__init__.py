"""The fairness check's seeded randomness: the synthetic population and the bootstrap.

Randomness lives here and never in `crossroads.engine` (constitution, principle II). The customer API
never imports this package, and nothing in it is stored: the report is a deterministic computation
from fixed seeds, cached in memory.
"""
