# Flink Project Management

This section addresses the Flink pipeline definition and management using [Confluent dbt](https://pypi.org/project/dbt-confluent/) plugin.

1. To be able to connect to Confluent Cloud, we need to set the environment variables for API keys and secrets. The following script loads those from Terraform output
    ```sh
    source ./scripts/set_env_from_tf.sh
    ```

    As an alternate source the .env file under apps/backend/

1. `dbt` needs models. The first layer is the references to existing CDC topics [see pipelines/models/sources.yaml](../pipelines/models/sources.yaml) file.

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
        description: Topic 'cdc.public.transactions' — registered via sl-dbt get-schema-existing-topic-to-dbt.
    ```

1. Be sure to modify your `.dbt/profiles.yml` with the following element.
    ```yaml
    cc_flink:
        outputs:
            dev:
                cloud_provider: '{{ env_var(''CC_PROVIDER'') }}'
                cloud_region: '{{ env_var('CC_REGION'') }}'
                compute_pool_id: '{{ env_var('FLINK_COMPUTE_POOL_ID'') }}'
                dbname: '{{ env_var('KAFKA_CLUSTER_NAME'') }}'
                environment_id: '{{ env_var('ENVIRONMENT_ID'') }}'
                execution_mode: streaming_query
                flink_api_key: '{{ env_var(''FLINK_API_KEY'') }}'
                flink_api_secret: '{{ env_var(''FLINK_API_SECRET'') }}'
                organization_id: '{{ env_var(''CC_ORG_ID'') }}'
                statement_label: dbt-confluent
                statement_name_prefix: dbt-
                threads: 4
                type: confluent
        target: dev
    ```

    This is a generic profile for Confluent Cloud  that uses environment variables to avoid sharing secrets in yaml file.

1. Continue to create the following flink statements to filter and transform raw CDC topics, create dimension and fact for the analytics.

The [path is pipelines/models/c360](../pipelines/models/c360)

| Source Table(s) | Folder Name | Sink Table | Goal |
| ----------------| ------------ |-----------|-----|
| cdc.public.accounts | sources | src_accounts | Deduplicate, flatten, filter, transform |
| cdc.public.customers | sources | src_customers | eduplicate, flatten, filter, transform |
| cdc.public.transactions| sources | src_transactions | eduplicate, flatten, filter, transform |
| src_customers | dimension |  dim_customers| Compute customer dimension |
| src_customers, src_account | dimension |  dim_customers| Compute transaction cross account metrics |
| dim_customers, | facts | fct_c360_profiles |

```sh
├── c360
│   ├── dimensions
│   │   ├── dim_account_tx_agg.sql
│   │   ├── dim_account_tx_agg.yml
│   │   ├── dim_customers.sql
│   │   ├── dim_customers.yml
│   │   ├── dim_transactions.sql
│   │   ├── dim_transactions.yml
│   │   ├── dim_tx_x_account.sql
│   │   └── dim_tx_x_account.yml
│   ├── facts
│   │   └── fct_c360_profile.sql
│   └── sources
│       ├── src_accounts.sql
│       ├── src_accounts.yml
│       ├── src_customers.sql
│       ├── src_customers.yml
│       ├── src_transactions.sql
│       └── src_transactions.yml
├── deploy_manifest.json
└── sources.yaml
```

Each model needs to have the table definition to create as sink. As an example the dimension to compute account aggregations look like ([file dim_account_tx_agg.sq](../pipelines/models/c360/dimensions/dim_account_tx_agg.sql)):

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
    data_type: DECIMAL
  - name: txn_total
    data_type: DECIMAL
  - name: last_transacted_at
    data_type: timestamp_ltz
```

## Deploy

dbt supports different way to manage the dependencies. We can use tag, folder, or tree.

* Deploy all the sources that are the first level of flink statements to deploy
```sh
# within the pipelines folder:
dbt run --select c360.sources --full-refresh
```
* Deploy the facts and its parents

```sh
# within the pipelines folder:
dbt run --select +c360.facts.fct_c360_profile
# Deploy other product
dbt run --select +crm.facts
```

## Undeploy

1. As dbt does not support undeploying, we need another tool to manage the drop table and undeploy statement. The [flink-tools-for-agents](https://github.com/jbcodeforce/flink-tools-for-agents/tree/main/tools/flink) includes tools to define a manifest of metadata about existing statements and then perform deplooy, undeploy and drop tables. 
    ```sh
    cd flink-tools-for-agents 
   v
    # OR
    uv run generate-manifest --sql-dir ../streamhouse_c360_demo/pipelines/models --overwrite 
    ```

    Drop tables listed in the `drop_tables` element of the manifest
    ```sh
    uv run flink-sql-deploy  --sql-dir ../streamhouse_c360_demo/pipelines/models drop-tables --group fraud
    uv run flink-sql-deploy --sql-dir ../streamhouse_c360_demo/pipelines/models drop-tables --group crm
    uv run flink-sql-deploy --sql-dir ../streamhouse_c360_demo/pipelines/models drop-tables --group c360 
    ```

### IaC

* Remove connector
    ```sh
    ./scripts/tf_connector.sh destroy
    ```

* Remove Confluent Cloud resources
    ```sh
    ./scripts/tf.sh destroy
    ```

* Remove AWS resources
    ```sh
    ./scripts/tf_aws.sh destroy
    ```