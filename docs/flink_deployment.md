# Flink Project Management with dbt

!!! info "Version"
    **Last updated:** 2026-11-24

This section describes how the different Flink pipelines are defined, deployed and removed with the [Confluent dbt](https://pypi.org/project/dbt-confluent/) plugin. The dbt project is in the [`pipelines/`](https://github.com/jbcodeforce/streamhouse_c360_demo/tree/main/pipelines) folder.

*As of 11/24** all commands were performed on MacOS.

## Prerequisites

1. Be sure to get the last version of [Confluent dbt](https://pypi.org/project/dbt-confluent/), getting from PyPi: adapt the version in [pipelines/pyproject.toml](https://github.com/jbcodeforce/streamhouse_c360_demo/tree/main/pipelines/pyproject.toml)
  ```yaml
    dependencies = [
    "dbt-confluent>=0.6.0"
    ]
  ```

1. Start virtual environment to run dbt
  ```sh
  cd pipelines
  source .venv/bin/activate
  # if new version was specified
  uv sync
  ```

1. To connect to Confluent Cloud, dbt needs the API keys, secrets and ids as environment variables. This script loads them from the Terraform outputs (see [Defining Confluent Cloud Resources with Terraform](sre_ccloud_tf.md)):

    ```sh
    # still in pipelines
    source ../scripts/set_env_from_tf.sh
    ```

    As an alternative, load the `apps/backend/.env` file that the script writes:

    ```sh
    set -a; source apps/backend/.env; set +a
    ```

    Verify the settings via:
    ```sh
    printenv
    ```


1. Normally on brand new project, `dbt init` is run. [See Confluent dbt documentation](https://docs.confluent.io/cloud/current/flink/operate-and-deploy/deploy-flink-dbt.html#step-2-create-and-connect-a-dbt-project). Init build also a `$HOME/.dbt/profiles.yml` file that includes references to Confluent cloud environment (or other dbt backend).

1. Add the profile below to `~/.dbt/profiles.yml`. As of now, the profile name must be `j9r`, to match the value set as `profile` in [`dbt_project.yml`](https://github.com/jbcodeforce/streamhouse_c360_demo/blob/main/pipelines/dbt_project.yml). Align names if you change. The below declartion, for dbt to read everything from environment variables, so no secret is stored in the file:

    ```yaml
    j9r:
      outputs:
        dev:
          cloud_provider: "{{ env_var('CLOUD_PROVIDER') }}"
          cloud_region: "{{ env_var('CLOUD_REGION') }}"
          compute_pool_id: "{{ env_var('FLINK_COMPUTE_POOL_ID') }}"
          dbname: "{{ env_var('KAFKA_CLUSTER_NAME') }}"
          environment_id: "{{ env_var('FLINK_ENV_ID') }}"
          execution_mode: streaming_query
          flink_api_key: "{{ env_var('FLINK_API_KEY') }}"
          flink_api_secret: "{{ env_var('FLINK_API_SECRET') }}"
          organization_id: "<your-confluent-organization-id>"
          statement_label: dbt-confluent
          statement_name_prefix: dbt-
          threads: 4
          type: confluent
      target: dev
    ```

    The `set_env_from_tf.sh` does not export the organization id. Get it from the Confluent Console, or with `confluent organization list`.

    The `compute_pool_id` of the profile is overridden per data product in `dbt_project.yml`: `c360` models run on `FLINK_COMPUTE_POOL_ID` and `crm` adn`fraud` models run on `FLINK_CRM_COMPUTE_POOL_ID`. This lets the Cost API attribute to present the cost per product.

## Pipeline definitions

### Sources

The first layer of models references the existing CDC topics, declared in [`pipelines/models/sources.yaml`](https://github.com/jbcodeforce/streamhouse_c360_demo/blob/main/pipelines/models/sources.yaml):

```yaml
version: 2
sources:
- name: cdc
  schema: "{{ env_var('KAFKA_CLUSTER_NAME') }}"
  tables:
  - name: customers
    identifier: cdc.public.customers
  - name: accounts
    identifier: cdc.public.accounts
    description: accounts information for a customer
  - name: transactions
    identifier: cdc.public.transactions
    description: Topic 'cdc.public.transactions'.
  - name: cards
    identifier: cdc.public.cards
    description: Topic 'cdc.public.cards'.
```

* Important to note that the database name for the `schema` entry, is defined as Kafka cluster name.

### Models

The models are organized by data product under [`pipelines/models`](https://github.com/jbcodeforce/streamhouse_c360_demo/tree/main/pipelines/models): `c360`, `crm` and `fraud`. Each product has a `sources`, `dimensions` and `facts` folder, and each model has a `.sql` file and a `.yml` file. Models are linked with `ref()`, so a model can depend on a model of another product: the `c360` dimensions use `src_accounts` and `dim_customers` from `crm`.

```sh
models
├── c360
│   ├── dimensions
│   │   ├── dim_account_tx_agg.{sql,yml}
│   │   ├── dim_transactions.{sql,yml}
│   │   └── dim_tx_x_account.{sql,yml}
│   ├── facts
│   │   ├── fct_c360_profile.{sql,yml}
│   │   ├── fct_crm_summary.{sql,yml}
│   │   ├── fct_hourly_tx_metrics.{sql,yml}
│   │   └── fct_merchant_streak.{sql,yml}
│   └── sources
│       └── src_transactions.{sql,yml}
├── crm
│   ├── dimensions
│   │   └── dim_customers.{sql,yml}
│   ├── facts
│   │   ├── fct_crm_by_country.{sql,yml}
│   │   ├── fct_crm_by_gender.{sql,yml}
│   │   ├── fct_crm_by_generation.{sql,yml}
│   │   └── fct_crm_by_segment.{sql,yml}
│   └── sources
│       ├── src_accounts.{sql,yml}
│       ├── src_cards.{sql,yml}
│       └── src_customers.{sql,yml}
├── fraud
│   └── facts
│       ├── fct_fraud_probe.{sql,yml}
│       └── fct_smb_spike.{sql,yml}
├── deploy_manifest.json
└── sources.yaml
```

| Model | Product | Inputs | Materialization | Goal |
| ----- | ------- | ------ | --------------- | ---- |
| `src_transactions` | c360 | `cdc.public.transactions` | streaming table | Deduplicate, flatten, filter, transform |
| `src_accounts` | crm | `cdc.public.accounts` | streaming table | Deduplicate, flatten, filter, transform |
| `src_cards` | crm | `cdc.public.cards` | streaming table | Deduplicate, flatten, filter, transform |
| `src_customers` | crm | `cdc.public.customers` | streaming table | Deduplicate, flatten, filter, transform |
| `dim_customers` | crm | `src_accounts`, `src_cards`, `src_customers` | streaming table | Customer dimension, with its accounts and cards |
| `dim_transactions` | c360 | `src_transactions`, `src_customers`, seeds `currency_codes` and `country_codes` | materialized table | Enrich transactions with currency, customer and country |
| `dim_account_tx_agg` | c360 | `src_accounts`, `dim_transactions` | materialized table | Transaction aggregates per account |
| `dim_tx_x_account` | c360 | `dim_customers`, `dim_account_tx_agg` | materialized table | Transaction and account metrics per customer |
| `fct_c360_profile` | c360 | `dim_customers`, `dim_tx_x_account` | materialized table | Customer 360 profile, served by the RTCE Lightning API |
| `fct_crm_summary` | c360 | `fct_c360_profile` | materialized table | CRM analytics, served by the RTCE Lightning API |
| `fct_merchant_streak` | c360 | `src_transactions` | streaming table | CEP: three or more consecutive transactions in the same merchant category |
| `fct_crm_by_country`, `_by_gender`, `_by_generation`, `_by_segment` | crm | `dim_customers` | materialized table | CRM aggregates |
| `fct_fraud_probe` | fraud | `src_transactions` | streaming table | CEP: small card-test charge followed by large charges |
| `fct_smb_spike` | fraud | `src_transactions`, `src_customers` | streaming table | CEP: large debits followed by a credit on an SMB account |

Each model needs the definition of the table it creates as sink. As an example, here is the [`dim_account_tx_agg.yml`](https://github.com/jbcodeforce/streamhouse_c360_demo/blob/main/pipelines/models/c360/dimensions/dim_account_tx_agg.yml) file of the dimension that computes the account aggregations:

```yaml
models:
- name: dim_account_tx_agg
  description: "Aggregates cross account"
  config:
    contract:
      enforced: true
  columns:
  - name: account_id
    data_type: varchar(2147483647)
    constraints:
      - type: not_null
      - type: primary_key
        expression: "not enforced"
  - name: customer_id
    data_type: string
  - name: account_type
    data_type: string
  - name: account_status
    data_type: string
  - name: balance
    data_type: DECIMAL
  - name: txn_count
    data_type: BIGINT
  - name: txn_total
    data_type: DECIMAL
  - name: last_transacted_at
    data_type: timestamp_ltz
```

[To get some tricks and how tos, see this chapter](https://jbcodeforce.github.io/flink-studies/coding/dbt/#how-to)

## Deploy

dbt can select the models to deploy by tag, folder or dependency tree. Run the commands from the `pipelines` folder.

* Load the reference data (the `country_codes` (ISO 3166-1 country codes) and `currency_codes` (ISO 4217 currency codes) seeds), needed by `dim_transactions`:

    ```sh
    uv run dbt seed
    ```

* Deploy the sources, which are the first level of Flink statements:

    ```sh
    uv run dbt run --select c360.sources crm.sources --full-refresh
    ```

* Deploy a fact table and all its parents:

    ```sh
    uv run dbt run --select +c360.facts.fct_c360_profile
    ```

* Deploy the other products:

    ```sh
    uv run dbt run --select +crm.facts
    uv run dbt run --select +fraud.facts
    ```

After editing a query, run `dbt run --full-refresh` on the model to redeploy it. This is required for the CEP models (`fct_merchant_streak`, `fct_fraud_probe`, `fct_smb_spike`).

## Undeploy

dbt does not support undeploying. The [flink-tools-for-agents](https://github.com/jbcodeforce/flink-tools-for-agents/tree/main/tools/flink) project provides tools that use a manifest of the existing statements to deploy, undeploy and drop tables. This repository has one in [`pipelines/models/deploy_manifest.json`](https://github.com/jbcodeforce/streamhouse_c360_demo/blob/main/pipelines/models/deploy_manifest.json). It defines:

* the statement groups `c360_pipeline`, `crm_pipeline` and `fraud_pipeline`, in deploy order;
* the `drop_tables` groups `c360`, `crm`, `fraud`, `cdc`, `connect` and `seeds`.

1. Regenerate the manifest if models were added or removed (the clone of `flink-tools-for-agents` is next to this repository):

    ```sh
    cd flink-tools-for-agents
    uv run generate-manifest --sql-dir ../streamhouse_c360_demo/pipelines/models --overwrite
    ```

1. Drop the tables listed in the `drop_tables` element of the manifest:

    ```sh
    uv run flink-sql-deploy --sql-dir ../streamhouse_c360_demo/pipelines/models drop-tables --group fraud
    uv run flink-sql-deploy --sql-dir ../streamhouse_c360_demo/pipelines/models drop-tables --group crm
    uv run flink-sql-deploy --sql-dir ../streamhouse_c360_demo/pipelines/models drop-tables --group c360
    ```

## Remove the infrastructure

Destroy the Terraform modules in the reverse order of their creation. `IaC/ccloud` comes last, because `IaC/rtce` and `IaC/connector` read its state. Skip the modules you did not apply.

* Remove the RTCE topics and Global API key:

    ```sh
    cd IaC/rtce && terraform destroy
    ```

* Remove the app host (needs AWS credentials):

    ```sh
    ./scripts/tf_ec2.sh destroy
    ```

* Remove the managed connector:

    ```sh
    ./scripts/tf_connector.sh destroy
    ```

* Remove the AWS resources:

    ```sh
    ./scripts/tf_aws.sh destroy
    ```

* Remove the Confluent Cloud resources:

    ```sh
    cd IaC/ccloud && terraform destroy
    ```

For the local PostgreSQL and Debezium containers, see [Local CDC](local_cdc.md#4-stop-and-reset).

