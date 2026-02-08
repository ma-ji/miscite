.PHONY: help dev worker sync-rw sync-predatory check db-upgrade db-check db-current db-heads db-revision

help:
	@echo "Targets:"
	@echo "  make dev       - run the web app"
	@echo "  make worker    - run the background worker"
	@echo "  make sync-rw   - sync Retraction Watch dataset"
	@echo "  make sync-predatory - sync predatory lists"
	@echo "  make check     - compile server modules"
	@echo "  make db-upgrade - apply DB migrations"
	@echo "  make db-check   - verify DB is at migration head"
	@echo "  make db-current - print current applied DB revision"
	@echo "  make db-heads   - print code migration head(s)"
	@echo "  make db-revision msg=\"...\" - create a new migration revision"

dev:
	python -m server.migrate upgrade
	python -m server.main

worker:
	python -m server.migrate upgrade
	python -m server.worker

sync-rw:
	python -m server.sync_retractionwatch

sync-predatory:
	python -m server.sync_predatory

check:
	python -m compileall -q server

db-upgrade:
	python -m server.migrate upgrade

db-check:
	python -m server.migrate check

db-current:
	python -m server.migrate current

db-heads:
	python -m server.migrate heads

db-revision:
	@if [ -z "$(msg)" ]; then echo 'Usage: make db-revision msg="your message"'; exit 2; fi
	python -m server.migrate revision -m "$(msg)"
