# Changelog

All notable changes to this project will be documented in this file.

## [0.1.0] — 2026-05-10

### Added
- Initial release with 4 journals: Nature, JAMA, NEJM, Lancet
- Plugin sub-folder structure: each journal owns `spec.yaml`, `palette.json`, `prompt.md`, `references.md`
- Python core: `theme_loader`, `matplotlib_applier`, `font_resolver`, `post_processor`, `caption_formatter`, `helpers`
- R core: `ggplot_applier.R`, `font_resolver.R`
- CLI scripts: `cheatsheet.py`, `validate_spec.py`, `rewrite.py`, `draft.py`
- Wave 1-3 integration with 8 biostats skills via `--style=<journal>` flag
- Acknowledgment of [Yuan1z0825/nature-skills](https://github.com/Yuan1z0825/nature-skills) (MIT)
