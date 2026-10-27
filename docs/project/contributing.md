<!-- The website shows the repository's CONTRIBUTING.md here. On GitHub, open ../../CONTRIBUTING.md. -->

--8<-- "CONTRIBUTING.md"

## Working on the documentation

The documentation is the Markdown in `docs/`. It reads well on GitHub and is built into a website with [Zensical](https://zensical.org) (the successor to Material for MkDocs), which reads `mkdocs.yml`:

```bash
python -m pip install -e ".[docs]"
zensical serve              # live preview at http://localhost:8000
zensical build --strict     # warnings, such as broken links, fail the build
```

Every Python example in the docs runs. To show what an example prints, put an empty block right after it:

````markdown
```text title="Output"
```
````

Then run `python tools/render_doc_outputs.py`, which runs the page and fills in the real output. `tests/test_docs.py` fails if any shown output no longer matches what the code prints, so the docs can't drift from the package. Start a code block with `# not run` if it only illustrates.

A few habits keep the docs readable: start a page with the problem it solves, show a small real example before any options, explain *why* in plain sentences, and save tables for genuine reference lists.
