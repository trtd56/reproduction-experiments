# Publishing Checklist

Use this before creating the GitHub repository.

- [ ] Publish from the `reproduction-experiments/` directory, not the private workspace root.
- [ ] Keep the repository focused on the Japanese proxy experiments.
- [ ] Confirm `PUBLICATION_MANIFEST.md` matches the final file tree.
- [ ] Confirm `SAFETY.md` is included and linked from `README.md`.
- [ ] Do not commit `data/` or `adapters/`.
- [ ] Do not commit full model prediction files if they contain copied dataset prompts or responses.
- [ ] Keep only aggregate summaries under `results/`.
- [ ] Confirm dataset and model names are attributed in `README.md`.
- [ ] Add a license only after deciding the intended reuse terms.
- [ ] Decide whether to add a DOI, citation entry, or release tag.
- [ ] Link the blog article and podcast page after they are published.
- [ ] If publishing trained adapters separately, document that they are intentionally backdoored research artifacts.
