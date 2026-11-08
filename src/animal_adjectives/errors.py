"""Project exceptions, so callers can tell expected failures from real bugs."""


class AnimalAdjectivesError(Exception):
    """Base class: the CLI turns these into a clean message and an exit code."""


class PageStructureError(AnimalAdjectivesError):
    """The Wikipedia page no longer looks the way the parser expects.

    This is fatal on purpose. Wikipedia pages get edited, and a confident but
    empty report would be much worse than a loud failure.
    """


class ImageDownloadError(AnimalAdjectivesError):
    """One image could not be fetched. Fatal for that image, not for the run."""
