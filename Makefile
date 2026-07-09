PYTHON ?= python

    setup:
	$(PYTHON) -m pip install -r requirements.txt

    validate-data:
	$(PYTHON) -m src.ingest.validate_local_files

    ingest:
	$(PYTHON) -m src.ingest.validate_local_files

    process:
	$(PYTHON) -m src.processing.clean_calls
	$(PYTHON) -m src.processing.clean_weather
	$(PYTHON) -m src.processing.clean_geography
	$(PYTHON) -m src.processing.build_features

    sqlite:
	$(PYTHON) -m src.database.load_sqlite
	$(PYTHON) -m src.database.run_sqlite_queries

    spark:
	$(PYTHON) -m src.processing.spark_transform

    model:
	$(PYTHON) -m src.models.train_cluster_model
	$(PYTHON) -m src.models.train_demand_model
	$(PYTHON) -m src.models.train_deep_learning_model
	$(PYTHON) -m src.models.evaluate_models

    report:
	$(PYTHON) -m src.reporting.build_hex_outputs
	$(PYTHON) -m src.reporting.build_tableau_outputs
	$(PYTHON) -m src.reporting.generate_summary_memo
	$(PYTHON) -m src.reporting.generate_charts

    excel:
	$(PYTHON) -m src.reporting.build_excel_planner

    hex:
	$(PYTHON) -m src.reporting.build_hex_outputs

    app:
	streamlit run src/app/streamlit_app.py

    mongodb:
	$(PYTHON) -m src.ingest.load_to_mongodb

    all: validate-data process sqlite model report excel spark mongodb
