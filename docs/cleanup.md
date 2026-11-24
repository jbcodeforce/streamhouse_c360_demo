# Cloud Resource Cleanup

!!! info "Version"
    **Last updated:** 2026-11-24


There are different cleaning operations to perform depending on the need.

1. Undeploy Flink statements and drop intermediate and sink flink tables
1. Reset all the data of the application
1. Migrate part of one Flink pipeline
1. Teardown AWS resources
1. Tear down Confluent Cloud resources


## Undeploy Flink Statements

* Stop all statements with dropping tables (need [the flink-tools-for-agents repo](https://github.com/jbcodeforce/flink-tools-for-agents)) to access some extra tools.
    ```sh
    git clone https://github.com/jbcodeforce/flink-tools-for-agents
    cd ../flink-tools-for-agents/
    uv run flink-sql-deploy --sql-dir ../streamhouse_c360_demo/pipelines/models undeploy --group crm_pipeline

    uv run flink-sql-deploy --sql-dir ../streamhouse_c360_demo/pipelines/models undeploy --group fraud_pipeline

    uv run flink-sql-deploy --sql-dir ../streamhouse_c360_demo/pipelines/models undeploy --group c360_pipeline
    ```

The flink-sql-deploy tools uses the `confluent-sql` Python library to access the Confluent Cloud flink REST API to manage statements. It uses a `deploy_manifest.json` file to keep flink statement metadata.

## Cleaning Materialized Tables

Because Flink statements that manage materialized tables are hidden, we need to drop the tables.

```sh
uv run flink-sql-deploy --sql-dir ../streamhouse_c360_demo/pipelines/models drop_tables --group crm

uv run flink-sql-deploy --sql-dir ../streamhouse_c360_demo/pipelines/models drop_tables --group c360

uv run flink-sql-deploy --sql-dir ../streamhouse_c360_demo/pipelines/models drop_tables --group fraud
```

The drop_tables command is taking into account materialized tables versus streaming tables.

## Cleaning CDC and Kafka  Connect Topics

The manifest also includes group definition for external topics.

```sh
uv run flink-sql-deploy --sql-dir ../streamhouse_c360_demo/pipelines/models drop_tables --group cdc

uv run flink-sql-deploy --sql-dir ../streamhouse_c360_demo/pipelines/models drop_tables --group connect
```

## Demonstration Reset

* Stop webapp and backend
    ```sh
    ./scripts/stop_dev.sh
    ```

* Stop postgresql local server
    ```sh
    cd IaC/local
    ./pg_local_server.sh --stop
    ```
* Debezium connector reset
    ```sh
    ./IaC/local/start_debezium.sh --full-reset
    ```


## AWS resources teardown

* Remove deployed app in EC2
    ```sh
    cd IaC/EC2
    terraform destroy
    ```
* Remove RDS and network configuration
    ```sh
    cd IaC/AWS
    terraform destroy
    ```

## Confluent Cloud resource teardown

* If you used managed Kafka connectors
    ```sh
    cd IaC/connector
    terraform destroy
    ```

* Remove Global API keys and service account for real-context engine
    ```sh
    cd IaC/rtce
    terraform destroy
    ```

* Remove compute pools, kafka cluster...
    ```sh
    cd IaC/ccloud
    terraform destroy
    ```

