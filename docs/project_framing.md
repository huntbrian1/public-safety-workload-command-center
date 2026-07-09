# Project Framing

## Problem Solved

Public safety service-event metadata is rich but often fragmented across large CSVs, weather feeds, calendar context, and geographic zone files. This project creates a local analytics system that turns those sources into workload visibility, resource-planning intelligence, and product/service recommendations.

## Job Description Mapping

- Consolidates diverse large-scale data sources.
- Cleans, integrates, and structures operational metadata.
- Uses SQL, machine learning, and reporting outputs to communicate insights.
- Produces recommendations for client service and product stakeholders.

## Why SQLite

SQLite provides a portable local analytics layer. It is easy to inspect, requires no server, and supports a credible SQL workflow for portfolio review.

## Why Hex

Hex is the first polished reporting layer because CSV exports can be uploaded directly, SQL/Python cells can reproduce the analysis narrative, and the final report can read like a stakeholder-facing analytics app.

## Why PySpark

PySpark demonstrates scalable processing for the 10M+ row use case. The local fallback keeps the project runnable on a laptop while documenting how Spark would handle larger runs.

## Why MongoDB

MongoDB stores raw/semi-structured records before transformation. This demonstrates a raw metadata layer without requiring it for the core local pipeline.

## Responsible ML

Clustering and forecasting are used for aggregate planning signals. The project does not make individual-level recommendations and does not overclaim model performance.
