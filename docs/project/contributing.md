<!-- The website shows the repository's CONTRIBUTING.md here. On GitHub, open ../../CONTRIBUTING.md. -->

--8<-- "CONTRIBUTING.md"

## Working on the documentation

The documentation is the Markdown in `docs/`. It reads well on GitHub and is built into a website with MkDocs Material:

```bash
python -m pip install -e ".[docs]"
python -m mkdocs serve      # live preview at http://127.0.0.1:8000
python -m mkdocs build --strict
```

Every Python example in the docs is run by `tests/test_docs.py`, so examples must work as written. Use a `text` code block for output, and start a block with `# not run` if it only illustrates.
