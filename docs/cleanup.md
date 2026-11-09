# Cleanup

There are different cleaning operations to perform depending of the needs.

1. Undeploying Flink Statements and drop intermediate, sink tables
1. Reset all the data of the application
1. Migrate part of one Flink pipeline
1. Teardown AWS resources
1. Teardown Confluent cloude resources 


## Undeploy Statements

* Stop all statements with dropping tables (need [another repo](https://github.com/jbcodeforce/flink-tools-for-agents))
    ```sh
    cd ../flink-tools-for-agents/
    uv run flink-sql-deploy --sql-dir ../streamhouse_c360_demo/pipelines/models undeploy --group crm_pipeline

    uv run flink-sql-deploy --sql-dir ../streamhouse_c360_demo/pipelines/models undeploy --group fraud_pipeline

    uv run flink-sql-deploy --sql-dir ../streamhouse_c360_demo/pipelines/models undeploy --group c360_pipeline
    ```

## Cleaning Materialized Tables

Because Flink statements to manage Materialized table are hidden, we need to drop the tables.

```sh
uv run flink-sql-deploy --sql-dir ../streamhouse_c360_demo/pipelines/models drop_tables --group crm

uv run flink-sql-deploy --sql-dir ../streamhouse_c360_demo/pipelines/models drop_tables --group c360

uv run flink-sql-deploy --sql-dir ../streamhouse_c360_demo/pipelines/models drop_tables --group fraud
```

## Cleaning topics

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

* If you used Managed kafka connectors
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