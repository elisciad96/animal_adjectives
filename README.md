# Animal Adjectives

Reads Wikipedia's [List of animal names](https://en.wikipedia.org/wiki/List_of_animal_names)
and writes an HTML report of every **collateral adjective** with all the **animals**
that belong to it. Each animal's picture is downloaded locally, and the report links
to the local copy. An animal with several adjectives appears under each of them.

## Setup and usage

Requires Python 3.10 or newer.

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

python -m animal_adjectives      # writes output/animal_adjectives.html
```

| Option | Default | Meaning |
|---|---|---|
| `-o`, `--output` | `output/animal_adjectives.html` | Report file |
| `--image-dir` | `/tmp` | Where pictures are stored |
| `-w`, `--workers` | `8` | Concurrent download threads |
| `-v`, `--verbose` | off | Debug logging |

The exit code is `0` on success, even if some pictures are missing (they are listed in
the log and shown as a placeholder in the report). It is `1` if the page cannot be
fetched or understood, and in that case no report is written.

On Windows, `/tmp` means `\tmp` on the current drive, usually `C:\tmp`.

## Tests

```bash
pytest                           # fast and offline
pytest --cov=animal_adjectives   # with coverage
pytest -m network                # checks the parser against the live page
ruff check .                     # lint
mypy                             # type-check (settings in pyproject.toml)
```

The same lint, type-check and offline tests run on every push via GitHub Actions
([.github/workflows/ci.yml](.github/workflows/ci.yml)), on Python 3.10 and 3.13.

## Packaging for submission

Build the archive from git rather than zipping the folder, so caches, coverage
data, build metadata and generated output (everything in `.gitignore`) stay out:

```bash
git archive --format=zip -o animal_adjectives.zip HEAD
```

## Architecture

| Module | Responsibility |
|---|---|
| `config.py` | Immutable run settings |
| `models.py` | `Animal`, `AnimalRecord` and `Catalog` types |
| `errors.py` | Project exceptions |
| `http_client.py` | Timeouts, retries and one session per thread |
| `parser.py` | HTML to records. The only module that knows the page's layout |
| `catalog.py` | Inverts records into adjective -> animals, merging duplicates |
| `images.py` | Finds and downloads pictures concurrently |
| `report.py` | Catalog to HTML |
| `pipeline.py` | Runs the steps in order |
| `cli.py` | Arguments, logging and exit codes |

## Design decisions

- **Threads for downloads.** The work is I/O-bound, so threads are effective despite the
  GIL. Workers return values and the main thread collects them, so no locks are needed.
- **Tables are expanded into a real grid.** Rowspans on the page shift later rows'
  columns, so reading the Nth `<td>` silently gives wrong results.
- **Both adjective tables are read.** Some adjectives, such as "avian", appear only in
  the "Generic terms" table.
- **Animals are identified by article URL.** The tables spell the same animal
  differently, and the URL lets them merge into one entry with one picture.
- **Lead images come from Wikipedia's REST summary API**, which is more reliable than
  scraping the first `<img>` of an article.
- **Failures are handled by severity.** A missing picture is a warning, while a page
  that can't be parsed stops the run rather than producing an empty report.
- **Files are written atomically**, so an interrupted run can't leave a truncated image
  that would later be mistaken for a complete cached one.

## Known limitations

- Animals with no collateral adjective on the page are not in the report, because it
  is organised by adjective.
- Qualifiers are dropped: `taurine (male)` is reported as `taurine`.
- An animal whose article has no lead image gets a placeholder. Currently that is only
  Dogfish, whose link leads to a disambiguation page.
- Pictures are cached by file name. Delete them from the image directory to fetch
  fresh copies.
- The report's links are absolute `file://` paths, so they work only on the machine
  that generated it.
