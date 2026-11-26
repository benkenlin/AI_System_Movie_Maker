PYTHON ?= python

.PHONY: install test validate ui film
install:
	$(PYTHON) -m pip install -e ".[all]"

test:
	$(PYTHON) -m pytest -q

validate:
	ai-content validate storyboard.json

ui:
	streamlit run ui/app.py

film:
	ai-content film storyboard.json --output outputs --licenses model_licenses.json --consent consent_registry.json
