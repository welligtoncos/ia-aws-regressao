# Critérios de promoção do modelo champion

Regras implementadas em [`workloads/shared/model_registry.py`](../workloads/shared/model_registry.py) (espelhado em `glue_bundle/` no deploy Glue).

## Métrica primária: WAPE

Para previsão de **saldo monetário**, o WAPE é a métrica primária de promoção:

- Interpretável para negócio (“erramos X% do saldo total no holdout”).
- Comparável entre retreinos com volumes diferentes.
- RMSE permanece registrado, mas **não** define promoção (pode subir quando a base fica mais difícil ou com mais outliers).

## Regra objetiva (todos os critérios)

Um novo run só vira champion se **já existir champion** e:

| # | Critério | Constante | Descrição |
|---|----------|-----------|-----------|
| 1 | **WAPE** | `CHAMPION_MIN_WAPE_IMPROVEMENT_PP = 1.0` | Novo WAPE ≤ champion WAPE − **1 ponto percentual** |
| 2 | **R²** | `CHAMPION_MAX_R2_REGRESSION = 0.01` | Novo R² ≥ champion R² − **0,01** |
| 3 | **Volume** | — | `total_linhas` do treino ≥ `total_linhas` gravado no champion |

Sem champion anterior → **primeira promoção** automática.

Constantes ajustáveis no código; após mudança, reenviar bundle Glue (`upload_glue_assets.ps1`).

## Caso validado (Rafo044, maio/2026)

| | Champion antigo | Candidato (reconcile) |
|---|-----------------|------------------------|
| `modelo_versao` | `xgb-saldo-v1-f42fcdfe` | `xgb-saldo-v1-460f98ec` |
| WAPE | 24,29% | **20,45%** (−3,84 p.p.) ✅ |
| R² | 0,8368 | **0,8453** ✅ |
| `total_linhas` | 6.819 | **12.168** ✅ |
| RMSE | 1473,74 | 1543,32 (pior, esperado) |

Com a regra nova, o candidato **deve ser promovido** no próximo retreino após deploy do bundle.

**Por que RMSE do candidato é maior?** Bases diferentes: champion treinado com merge parcial (menos meses/clientes, possivelmente menos outliers). WAPE e R² no holdout completo são mais representativos para negócio. Antes da mudança, RMSE ≥ 2% melhor bloqueava essa promoção.

## Versionamento da base

Cada promoção grava em `champion/metrics.json` e `champion_meta.json`:

- `total_linhas`
- `dataset_fingerprint` — hash `sha256(linhas|max_data_referencia)[:16]`

Compare fingerprints entre runs para detectar **data drift** antes de confiar na troca.

## Runs duplicados com mesmas métricas

Dois `run_id` com WAPE/R² idênticos (ex.: dois `--reconcile` seguidos) **não são bug**: mesmo CSV e mesma semente XGBoost geram o mesmo `modelo_versao`. São execuções distintas no histórico Athena; só a que **promove** grava `is_champion = true`.

## Boas práticas (roadmap)

| Prática | Status |
|---------|--------|
| Holdout temporal fixo para comparar runs | Já no pipeline (`temporal_train_val_test_split`) |
| WAPE primária + volume mínimo | Implementado |
| Fingerprint da base | Implementado |
| Holdout fixo persistido (mesmo conjunto de `cliente_id`/datas entre runs) | Evolução futura |
| Comparar só runs com mesmo `dataset_fingerprint` | Recomendado em comitês de modelo |

## Promover manualmente após deploy

```powershell
.\scripts\upload_glue_assets.ps1 -Bucket saldo-previsto-data-prod
python scripts/run_rafo044_experiment.py --reconcile --upload
```

Verifique no Athena:

```sql
SELECT run_id, ROUND(wape, 2) AS wape, ROUND(r2, 4) AS r2,
       total_linhas, is_champion, modelo_versao
FROM saldo_previsto_db_prod.tb_metricas_treino
ORDER BY dt_processamento DESC
LIMIT 5;
```

Confira `champion/metrics.json` no S3: `wape` ~20,45 e `total_linhas` 12168.

## Ver também

- [`ANALISE_METRICAS_ATHENA.md`](ANALISE_METRICAS_ATHENA.md) — validação em prod
- [`DATA_MODEL.md`](DATA_MODEL.md) — glossário `is_champion`
