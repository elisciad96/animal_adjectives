"""List Wikipedia's collateral adjectives with their animals, as an HTML report.

Module map, in the order the data flows through them:

    http_client -> parser -> catalog -> images -> report
                 (all of them coordinated by pipeline, started from cli)

Each module does one job, so each can be tested without the others.
"""

__version__ = "1.0.0"
