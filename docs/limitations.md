# Limitations

- Public data fields may be missing, delayed, duplicated, or inconsistently categorized.
- Timestamp parsing relies on available source formats and local hourly alignment.
- Weather joins assume Seattle local time and nearest lower-hour matching.
- Geography joins use beat/zone identifiers and should be validated against authoritative boundaries for production use.
- Sample mode is useful for portfolio iteration but may not represent the full distribution.
- Models predict aggregate high-demand zone-hour periods, not individual events.
- Forecasts should support operational planning, product/service analytics, and resource-planning visibility, not individual-level decisions.
- Cloud deployment files are support artifacts and require user-provided credentials and infrastructure choices.
