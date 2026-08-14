# CON-001 primary-annotation worksheet

This isolated offline Streamlit worksheet helps the dissertation researcher
construct the human-owned CON-001 before-only reference without editing JSON.
It is not part of the production application and imports no extraction,
provider, engine, baseline, or decision-policy modules.

Run from the repository root:

```text
.venv/bin/streamlit run evaluation/primary_annotation/streamlit_app.py
```

The app reads only the allowlisted frozen CON-001 before document. Working
drafts are mutable. Explicitly approved records are stored in versioned,
create-only directories under:

```text
evaluation/artifacts/primary_annotations/con-001/frozen/vNNN/
```

Each approved version contains separate current-state, private primary-decision
and approval-manifest records. A future reviewer-safe projection accepts only
the current-state record and rejects decision-reference fields.
