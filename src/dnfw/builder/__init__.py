"""The modular firmware builder (docs/builder.md): pick the parts, build the .syx from the
User's own Elektron files, in the browser (Pyodide, tools/web/builder.html) or on the command
line (scripts/dn2build.py), by the same code.

- parts: the catalogue (what can be left out, how it is grouped, what it costs).
- selection: the active choice, read once at import by the modules that emit code.
- sharcgen: every SHARC object regenerated for the choice (the generators + selas).
- cfpatch: the ColdFire's data for the choice (MACHINE SEL list, names).
- build: the pipeline, the budgets and the checks.
"""
