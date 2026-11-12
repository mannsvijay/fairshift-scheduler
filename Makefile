# Convenience targets. Every target is a plain `python -m fairshift ...` command,
# so Windows users can run the same commands without make.
PY ?= python3

.PHONY: starter full validate repro test docs sample clean

starter:            ## small dataset (seconds)
	$(PY) -m fairshift generate --scale starter

full:               ## brief's volume: 2,000 employees, 100 teams, 90 days, 5,000 leaves (~30 s)
	$(PY) -m fairshift generate --scale full

validate:           ## re-validate an existing output folder
	$(PY) -m fairshift validate --data out/starter

repro:              ## generate twice and compare checksums
	$(PY) -m fairshift repro --scale starter

test:
	$(PY) -m unittest -v

docs:               ## regenerate data dictionary + ERD from the schema
	$(PY) -m fairshift docs

sample:             ## refresh the committed sample output
	$(PY) -m fairshift generate --scale starter --out sample_output/starter
	$(PY) -m fairshift repro --scale starter --report sample_output/starter/reports/reproducibility_report.md

clean:
	rm -rf out
