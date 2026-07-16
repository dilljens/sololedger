.PHONY: install check status invoice expense tax

install:
	pip install -r requirements.txt

check:
	python -m app.main check

status:
	python -m app.main status

invoice:
	python -m app.main invoice create $(filter-out $@,$(MAKECMDGOALS))

expense:
	python -m app.main expense $(filter-out $@,$(MAKECMDGOALS))

tax-estimate:
	python -m app.main tax estimate

tax-deadlines:
	python -m app.main tax deadlines

tax-schedule-c:
	python -m app.main tax schedule-c

%:
	@:
