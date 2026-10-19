# Changelog

All notable changes to this project will be documented in this file.

This project aims to follow Keep a Changelog principles and Semantic Versioning.

## [Unreleased]

## [0.2.0] - 2026-10-19

### Added
- Interfaces now list the specific procedures they lump together (`module procedure` lists and interface bodies) under a "Procedures" field, cross-linked like type-bound procedures. Interface bodies are rendered with their signature, arguments and return value.
- `f:interface` lists (and links) the specific procedures of the parsed interface of the same name by default (a `:module:` option picks the module or submodule to look in). A `:procedures:` option overrides the list and warns about names unknown to the parsed interface.
- New "Interfaces" example page in the documentation.
- `FortranInterface` gains `procedures` (specific names) and `bodies` (explicit interface bodies), populated by both the regex and FORD lexers.

### Changed
- `f:module`/`f:submodule` render interfaces before procedures.

### Fixed
- Regex lexer: procedures declared inside interface blocks are no longer reported as module procedures. Abstract/unnamed interface blocks and `operator(...)`/`assignment(=)` generics are recognized.
- Private specific procedures reachable through a public generic interface are now documented, matching the existing behavior for type-bound procedures.

## [0.1.0] - 2026-03-04

### Added
- Initial project governance documents (`CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`).
- CI test matrix across supported Python versions.

### Changed
- Hardened runtime version detection for mixed editable/site-packages environments.
- Packaging metadata cleanup and alignment around `pyproject.toml`.
