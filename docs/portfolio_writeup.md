# Portfolio Writeup

This project simulates how a public safety technology provider could use service demand metadata to improve operational visibility, product analytics, and client service planning. I consolidated public safety call/service data with weather, calendar, and geographic metadata, cleaned and structured the data into an analytical model, applied clustering and machine learning to identify demand patterns, and built a Streamlit workload command center to communicate findings.

The project is intentionally built around operational workload, command center visibility, and client service analytics. It avoids enforcement oriented framing and focuses on aggregate resource planning intelligence.

## What I Built

  A repeatable Python pipeline from raw data validation through processed fact and feature tables.
  A PySpark full scale aggregation path to zone hour planning grain.
  Zone hour feature engineering for workload forecasting.
  KMeans clustering to identify operational demand profiles.
  Baseline, Random Forest, and MLP comparison models for high demand zone hour classification.
  A public Streamlit dashboard with period filters, map coverage, workload heatmaps, timing patterns, category mix, weather context, and data QA.
  Excel ready outputs for scenario planning and stakeholder review.

## Business Value

The platform turns fragmented service event metadata into planning signals: workload concentration, peak demand windows, category mix, cluster profiles, high demand predictions, and product/service recommendations.
