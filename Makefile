.PHONY: help dev worker sync-rw sync-predatory check

help:
	@echo "Targets:"
	@echo "  make dev       - run the web app"
	@echo "  make worker    - run the background worker"
	@echo "  make sync-rw   - sync Retraction Watch dataset"
	@echo "  make sync-predatory - sync predatory lists"
	@echo "  make check     - compile server modules"

dev:
	python -m server.main

worker:
	python -m server.worker

sync-rw:
	python -m server.sync_retractionwatch

sync-predatory:
	python -m server.sync_predatory

check:
	python -m compileall -q server
