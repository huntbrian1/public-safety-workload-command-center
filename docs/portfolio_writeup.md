# Portfolio Writeup

This project simulates how a public safety technology provider could use service-demand metadata to improve operational visibility, product analytics, and client service planning. I consolidated public safety call/service data with weather, calendar, and geographic metadata, cleaned and structured the data into an analytical model, applied clustering and machine learning to identify demand patterns, and built Hex, Tableau, and Excel-ready tools to communicate findings to product, service, and business stakeholders.

The project is intentionally built around operational workload, command-center visibility, and client service analytics. It avoids enforcement-oriented framing and focuses on aggregate resource-planning intelligence.

## What I Built

- A repeatable Python pipeline from raw data validation through processed fact and feature tables.
- A SQLite database with dimensional tables and query exports.
- Zone-hour feature engineering for workload forecasting.
- KMeans clustering to identify operational demand profiles.
- Baseline, Random Forest, and MLP comparison models for high-demand zone-hour prediction.
- Hex-ready, Tableau-ready, Excel-ready, and Streamlit-ready outputs.
- Optional support for PySpark, MongoDB, R validation, Docker, Kubernetes, AWS, and GCP.

## Business Value

The platform turns fragmented service-event metadata into planning signals: workload concentration, peak demand windows, category mix, cluster profiles, high-demand predictions, and product/service recommendations.
