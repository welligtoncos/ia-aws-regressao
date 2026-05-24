PYTHON ?= python
PIP ?= pip
TF_DIR = infra
ENV ?= dev

.PHONY: install test lint plan-dev plan-hom plan-prod apply-dev apply-hom apply-prod destroy-dev destroy-hom destroy-prod

install:
	$(PIP) install -r requirements.txt

test:
	$(PYTHON) -m pytest tests/ -v

lint:
	$(PYTHON) -m flake8 app/ scripts/ workloads/ tests/

generate-data:
	$(PYTHON) scripts/run_generate_dataset.py --local-only --clientes 5000 --meses 10

generate-data-s3:
	$(PYTHON) scripts/run_generate_dataset.py --clientes 5000 --meses 10 --bucket sample-data-dev

train-local:
	$(PYTHON) app/src/main.py --input-bucket sample-data-dev --output-bucket sample-data-dev

plan-dev:
	$(MAKE) plan ENV=dev

plan-hom:
	$(MAKE) plan ENV=hom

plan-prod:
	$(MAKE) plan ENV=prod

plan:
	cd $(TF_DIR) && terraform init -input=false && terraform plan -var-file=inventories/$(ENV)/terraform.tfvars

apply-dev:
	$(MAKE) apply ENV=dev

apply-hom:
	$(MAKE) apply ENV=hom

apply-prod:
	$(MAKE) apply ENV=prod

apply:
	cd $(TF_DIR) && terraform init -input=false && terraform apply -var-file=inventories/$(ENV)/terraform.tfvars -auto-approve

destroy-dev:
	$(MAKE) destroy ENV=dev

destroy-hom:
	$(MAKE) destroy ENV=hom

destroy-prod:
	$(MAKE) destroy ENV=prod

destroy:
	cd $(TF_DIR) && terraform init -input=false && terraform destroy -var-file=inventories/$(ENV)/terraform.tfvars -auto-approve
