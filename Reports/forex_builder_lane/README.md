# Forex Builder Lane Reports

The Forex builder planner prints a JSON plan to stdout. It does not create, replace, or delete report files.

- `ProposedJsonPath` and `ProposedMarkdownPath` identify suggested future locations only.
- The proposed packet text is embedded in the JSON report.
- Goals containing blocked terms return no next actions.
- The planner does not execute any listed command.

All outputs are planning previews and remain paper-only.
