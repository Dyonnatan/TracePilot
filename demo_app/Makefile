COMPOSE := docker compose
TELEMETRY_COMPOSE := docker compose -f ../docker-compose.yml -f ../docker-compose.hostmetrics.yml
SERVICES := shop-api payment-service chaos-control
VENV := .venv

.PHONY: telemetry up down down-all reset-db deploy-bad deploy-good ps logs test scenarios-table

## Sobe OpenObserve + Collector da raiz com o override de métricas de host.
telemetry:
	$(TELEMETRY_COMPOSE) up -d

## Sobe a stack de telemetria e o ambiente de referência.
up: telemetry
	$(COMPOSE) up -d --build

## Derruba só o ambiente de referência (telemetria continua de pé).
down:
	$(COMPOSE) down

## Derruba o ambiente de referência e a stack de telemetria.
down-all: down
	$(TELEMETRY_COMPOSE) down

## Recria o banco a partir de postgres/init.sql (apaga pedidos). Necessário
## quando o schema muda: o init.sql só roda com volume vazio.
reset-db:
	$(COMPOSE) rm -sfv postgres
	docker volume rm -f tracepilot-demo_postgres_data
	$(COMPOSE) up -d --wait postgres

## Cenário coupon_bug: deploy da versão 1.1.0 do shop-api.
deploy-bad:
	SHOP_VERSION=1.1.0 $(COMPOSE) up -d --no-deps shop-api

## Volta o shop-api para a versão 1.0.0.
deploy-good:
	SHOP_VERSION=1.0.0 $(COMPOSE) up -d --no-deps shop-api

ps:
	$(COMPOSE) ps

logs:
	$(COMPOSE) logs -f --tail=50

$(VENV)/bin/pytest: requirements-dev.txt $(foreach s,$(SERVICES),$(s)/requirements.txt)
	python3 -m venv $(VENV)
	$(VENV)/bin/pip install -q -r requirements-dev.txt
	touch $@

## Regenera a tabela de cenários do README a partir de scenarios/*.yaml.
scenarios-table: $(VENV)/bin/pytest
	$(VENV)/bin/python scripts/render_scenarios_table.py

## Roda os testes de cada serviço isoladamente (módulos main.py colidem).
test: $(VENV)/bin/pytest
	@for service in $(SERVICES); do \
		echo "== $$service"; \
		(cd $$service && OTEL_SDK_DISABLED=true ../$(VENV)/bin/python -m pytest -q) || exit 1; \
	done
