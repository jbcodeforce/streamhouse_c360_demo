# Demonstration Script

We may demonstrate the Streamhouse architecture in different ways, using one of the approaches implemented in this repository:

1. Local database, writing directly to Kafka topics defined within Confluent Cloud Kafka Cluster
2. Run Database on AWS, with Kafka Connector defined to get data from the database to Kafka topics. This approach has cost for the services on AWS.

For each the following activities are common:

1.  Deploy Confluent Cloud components: This step is to create Environment, Kafka cluster, schema registry, service accounts, api keys and secrets, and compute pools. We propose two approches to define the environment and components of this demonstration, one using the Confluent Console or one using Terraform:
    * [using Terraform](./sre_ccloud_tf.md).
    * [or using the Confluent cloud console](./sre_ccloud.md)
1. Optional: Deploy Database in AWS RDS with the needed [AWS components](./sre_aws.md) also using terraform. It includes the terraform definition to deploy Debezium CDC source connector on Confluent Cloud managed connector. This step is optional as the application can emulates CDC connector and use local database.
* [Deploying the Flink pipeline](./flink_deployment.md) to build the customer 360 analytics profile using Confluent dbt.
* [See dedicated 'demo script' note](./demo_script.md) to run the application with local components.

## Run with a remote database server

The architecture of the demonstration at the high-level looks like:

![](./diagrams/rds_execution.drawio.png)

Once the Confluent Cloud and AWS resources are created by Terraform, the user starts the local web application that connect to remote database server. To do this deployment see the [SRE doc](./sre_ccloud_tf.md)

* Set environment variables to access Confluent Cloud resources, like Kafka, schema Key/secret and bootstrap address:
    ```sh
    source ./scripts/set_env_from_tf.sh
    ```

    or use the .env file to create environment variables in your current terminal session:
    ```sh
    set -a
    source apps/backend/.env
    set +a
    ```
* Set environment variables to the .env file
    ```sh
    export ENV_CONFIG_FILE=./apps/backend/.env
    ```


* Start the local webapp with remote RDS database
    ```sh
    ./scripts/run_dev.sh --db rds
    ```

* [Follow with demonstration script](#demonstration-scenarios)

## Run with Local Database Get started locally

This time the database runs locally and the web app writes to kafka in parallel to write to database.

![](./diagrams/local_execution.drawio.png)

* Be sure to have the Confluent Cloud resources created with Terraform. To do this deployment see the [SRE doc](./sre_ccloud_tf.md)

* Start the local Postgresql server
    ```sh
     ./scripts/local_start_pg.sh 
    ```

    You should get some report like:
    ```
    ┌─────────────────────────────────────────────────────────┐
    │  Local PostgreSQL connection details                    │
    ├─────────────────────────────────────────────────────────┤
    │  Host     : localhost                                   │
    │  Port     : 5432                                        │
    │  Database : c360db                                      │
    │  User     : dbadmin                                     │
    │  Password : localdevonly                                │
    └─────────────────────────────────────────────────────────┘
    ```

* Set environment variables to access Confluent Cloud resources, like Kafka, schema Key/secrets and bootstrap address. This can be done by looking terraform output:
    ```sh
    source ./scripts/set_env_from_tf.sh
    ```

    or using your own scripts to get environment variables preset, to an existing Confluent Cloud environment.

* Set environment variables to the .env file
    ```sh
    export ENV_CONFIG_FILE=./apps/backend/.env
    ```

## Demonstration Scenarios

### Prepare backend environment

* Set where to find the specific `.env` file. You can use different .env file and reference it via environment variable:
    ```sh
    export ENV_CONFIG_FILE=$PWD/apps/backend/.env
    ```

* Start the local webapp
    ```sh
    ./scripts/run_dev.sh 
    ```


Changes written by the backend to PostgreSQL are published to the `cdc.public.*` topics by Debezium (see [Local CDC](local_cdc.md)); the backend does not produce to Kafka itself.

### Deploy the Flink Statements / Materialized Tables

* Deploy the Flink statements using dbt
    ```sh
    cd pipelines
    source .venv/bin/activate
    # verify the version, if need to update, change in pyproject.yaml in pipelines folder
    dbt version
    # Deploy the c360 data product from the fact table to the parents
    dbt run --select +c360.facts.fct_c360_profile
    ```

* Once all materialized tables are deployed, we need to enable RTCE on the fact table. There is a separate terraform to do so.
    ```sh
    cd IaC/rtce
    terraform apply
    ```

    Should output:
    ```sh
    Apply complete! Resources: 5 added, 0 changed, 0 destroyed.

    Outputs:

    rtce_lightning_api_key_id = "IOGMHHDUI22T7GPE"
    rtce_lightning_api_key_secret = <sensitive>
    rtce_lightning_sa_id = "sa-r2z9987"
    rtce_topic_name = "fct_c360_profile"
    ```

    Verify in the console that the `fct_c360_profile` topic is enabled:
    ![](./images/LT_in_topic.png)

* Update environment variables to be able to get the Global key and secret
    ```sh
    CONFLUENT_GLOBAL_KEY=$(terraform output -raw rtce_lightning_api_key_id)
    CONFLUENT_GLOBAL_SECRET=$(terraform output -raw rtce_lightning_api_key_secret)
    ```

    or to also modify the backend .env file rerun:
    ```sh
    ./scripts/set_env_from_tf.s
    ```


### Use the Web App

[http://localhost:5173/](http://localhost:5173/)

#### Customers Management

The customers page presents a list of existing customers loaded from the database:

![](./images/customers_page.png)

It is possible to add a new customer, with the Add customer button, or view, update, delete an existing customer using the action icon.

For example selecting the eye icon on James Carter brings this view:

![](./images/james_carter.png)

#### Accounts Management

The accounts page presents a list of accounts per customer loaded from the database:

![](./images/web_accounts.png)

This view is only for demonstration purpose. It is possible to add an account, but the real use case will be to add an account from the customer view. 

#### Transaction Management

The transactions page presents a list of current transactions in the database:

![](./images/web_tx.png)

Again this is for demonstration purpose.

To simulate a week of activity, click **Generate 200 transactions**. The backend creates 200 transactions on existing accounts, timestamped from 7 days ago in 15-minute increments, inserts them in Postgres, and Debezium publishes them to the `cdc.public.transactions` topic. The page then shows the newly created transactions (the list is not kept after a browser refresh).

### Data products view

This page demonstrates the presentation of Flink statement lineage and metrics per data analytics product. 

* First select the analytics product
    ![](./images/select-data-product.png)

* See the pipeline graph for one of the fact table:
    ![](./images/statement_graph.png)

* User can drill down to see real-time metrics for on of the statement, and the deployed SQL query:
    ![](./images/statement_metrics.png)

    The message in and out should be greater than 0 when there is record flowing into the topics.

*Recall:* the architecture to support this use case is presented in the figure below:
![]()

### Analytics Dashboard

The Analytics page is an illustration of what can be done by directly accessing data in kafka

1. Get the aggregation cross customers. Rather than pulling every customer row and folding it in the backend, the cross-customer aggregates are built in Flink as a **CRM analytic data product** — five small materialized tables (`fct_crm_summary`, `fct_crm_by_segment`, `fct_crm_by_generation`, `fct_crm_by_gender`, `fct_crm_by_country`) derived from `fct_c360_profile`. The backend reads them with five simple `SELECT *` **snapshot queries** run concurrently through the `confluent-sql` driver — the aggregation work stays in Flink and only the summary rows cross the wire. This is the Streamhouse pattern: build analytics products in Flink, expose them through a plain query.
    ![](./images/fct_c360_profile_db.png)

    The backend also returns the elapsed time from a client point of view. A snapshot query spins up a Flink statement, so each runs in roughly 5–8s; the five run concurrently so the dashboard load is bounded by the slowest, not their sum.

1. Use the snapshot query, which creates a Flink Statement, to get a data for a user:
    ![](./images/snap_query_carter.png)
    Same as above the query now has where condition on the customer name.

1. We can do the same query with the new Real-time context engine, lightning query:
    ![](./images/LT_execution_carter.png)

    We can see that it gets results in 605ms.

### Demonstrate Real-time Context Engine

There is a local LLM running in the background listening on http://localhost:7999/v1, so a OpenAPI compatible protocol. The backend is running an Agent with MCP tool defined in code, and the user interface support chatting with the customer 360 profile topic:

![](./images/querying_with_chat_rtce.png)

* Examples of query to ask:
    - What is the profile of Mr Carter?
    - what about Mrs Walsh profile?
    - What is the current CRM metrics?


### Verify data are in Postgresql tables. 

* Start a session in psql:
    ```sh
    container exec -it c360-postgres psql -U dbadmin -d c360db
    ```

    ```sql
    -- Row counts for all three tables
    SELECT 'customers'   AS tbl, COUNT(*) FROM customers
    UNION ALL
    SELECT 'accounts'    AS tbl, COUNT(*) FROM accounts
    UNION ALL
    SELECT 'transactions'AS tbl, COUNT(*) FROM transactions;

    -- Sample a customer with their accounts
    SELECT c.first_name, c.last_name, c.email, c.segment,
        a.account_type, a.balance
    FROM   customers c
    JOIN   accounts a USING (customer_id)
    LIMIT  10;

    -- Recent transactions
    SELECT t.transaction_type, t.amount, t.merchant_name,
        t.merchant_category, t.channel, t.status,
        t.transacted_at
    FROM   transactions t
    ORDER  BY t.transacted_at DESC
    LIMIT  10;

    -- Quit
    \q
    ```

### Cleanup

* Stop webapp
    ```sh
      ./scripts/stop_dev.sh
    ```
* Stop postgresql local server
* Undeploy flink statements:
    ```sh

    ```
* Destroy cloud resources with terraform, only if you need to clean Confluent cloud resources.
