
## Purpose

The purpose of this repository is to implement a Customer 360 streaming data pipeline integrating operational databases (PostgreSQL, DB2,...) with event streaming, Change Data Capture (CDC), and modern lakehouse analytical sinks. 

This is one possible demonstration of the [Streamhouse architecture](https://streamhouse.com) with Confluent Cloud products.

<figure markdown='span'>
![](./images/app/home_page.png)
<caption>**The home page of the application to drive the demonstration**</caption>
</figure>

From a business requirement point of view, **the goal is to demonstrate how to synchronize a change in business state everywhere it is used.**

The user story for the demonstration looks like: 

> as a data architect I want to deliver the business entities update to every system and person that depends on it, at the same time, so I can ensure no team operates on a **stale or conflicting copy** of that fact.

Streamhouse data architecture continuously captures and processes changes as they happen, governs that data, and makes the same trusted business context available to applications, agents and analytics without requiring another set of data copies and pipelines.

At the high level, Streamhouse reference architecture looks like in the figure below:

<figure markdown='span'>
![](./diagrams/stream-arch.drawio.png)
<caption>Streamhouse Capabilities</caption>
</figure>

The architecture delivers a capture layer to bring data in centralized messaging platform to transport and persist records defined in structured schemas. A layer of tranformation, data enrichment and data analytics construct helps to serve golden records to downstream processing. Those golden records, representing valuable business events or data analytic products can be consumed by AI Agents to build their own, fresh, context.

When applied the architecture to Confluent technology stack, Streamhouse is supported by the following components:

<figure markdown='span'>
![](./diagrams/stream-cc-arch.drawio.png)
<caption>Streamhouse With Confluent Cloud</caption>
</figure>

1. The **capture** is done by different Kafka source connectors
1. The **transport** is supported by Kafka Brokers and topics, with contracts in Schema Registry
1. **Transform** is done by Confluent Cloud for Flink. with stateless or stateful logic to build golden records and business events
1. **Serve** is supported by Flink with snapshot queries, by Kafka Sink connectors and Tableflow to write Iceberg Tables to object storage. Real-time context engine is also a serving layer for AI Agents.
1. **Governance**: is done by schema registry and other end-to-end governance capabilities.

## Capabilities demonstrated

### Hybrid ingestion

One of the path of the demonstration is to run database and Debezium connector on local servers, (the user laptop to make the demonstration simpler). The CDC can be connected to a Confluent Cloud Kafka cluster, creates the expected topics, and schemas and then process changes from the source database to the kafka topics:

![](./diagrams/hybrid/comp_view.drawio.png)

[See detail in this note](./local_cdc.md) on how to run this approach.

### CDC Managed Connector

The alternate to the previous deployment is to get the database accessible from Confluent Cloud VPC and use managed connector deployment. 

* [See this note for terraform based deployment](./sre_ccloud_tf.md#defining-confluent-cloud-resources-with-the-terraform)
* [See this note for Confluent Cloud Console driven deployment](./sre_ccloud.md#create-debezium-cdc-v2-kafka-connector)

### Infrastructure as Code

The Confluent cloud resources are created with Terraform, for Kafka cluster, default topics, service accounts, role-bindings, API keys and secrets.
One important aspect of the deployment is to isolate data products in their own compute pool, and to isolate Flink snapshot queries on at least one compute pool:


![](./diagrams/flink-cp.drawio.png)

[See this note for details](./sre_ccloud_tf.md)

### CDC envelop automatic processing to upsert tables

When created by Debezium connector the created tables have a changelog.mode set to retract if the source table in the SQL database has not primary key.

```sql
WITH (
  'changelog.mode' = 'retract',
  'kafka.cleanup-policy' = 'delete',
  'key.format' = 'avro-registry',
  'scan.startup.mode' = 'earliest-offset',
  'value.format' = 'avro-debezium-registry'
)
```

Still it is possible to alter the default settings so develop can work on the CDC envelop and operation. This pattern is demonstrated for the `cdc.public.customers`, [in this SQL](https://github.com/jbcodeforce/streamhouse_c360_demo/blob/main/pipelines/models/crm/sources/src_customers.sql)

```sql
 SELECT
    customer_id,
    coalesce(IF(op= 'd', before.first_name, after.first_name), 'NULL') as first_name,
    coalesce(IF(op= 'd', before.last_name, after.last_name), 'NULL') as last_name,
    coalesce(IF(op= 'd', before.email, after.email), 'NULL') as email,
    coalesce(IF(op= 'd', before.phone, after.phone), 'NULL') as phone,
    TO_TIMESTAMP_LTZ(IF(op= 'd', before.date_of_birth, after.date_of_birth), 'yyyy-MM-dd''T''HH:mm:ss.SSSSSS''Z''') as date_of_birth,
    coalesce(IF(op= 'd', before.gender, after.gender), 'NULL') as gender,
    TO_TIMESTAMP_LTZ(IF(op= 'd', before.created_at, after.created_at), 'yyyy-MM-dd''T''HH:mm:ss.SSSSSS''Z''') as registration_date,
    coalesce(IF(op= 'd', before.segment, after.segment), 'NULL')   as customer_segment,
    TO_TIMESTAMP_LTZ(IF(op= 'd', before.customer_since, after.customer_since), 'yyyy-MM-dd''T''HH:mm:ss.SSSSSS''Z''') as customer_since,
    coalesce(IF(op= 'd', before.city, after.city), 'NULL') as city,
    coalesce(IF(op= 'd', before.state, after.state), 'NULL') as state,
    coalesce(IF(op= 'd', before.postal_code, after.postal_code), 'NULL') as postal_code,
    coalesce(IF(op= 'd', before.country, after.country), 'NULL') as country,
    `$rowtime` as event_ts
    FROM {{ source('cdc', 'customers') }}
```

### DBT deployment, Materialized and Streaming tables

Confluent has developed two Python modules: [`dbt-confluent`](https://pypi.org/project/dbt-confluent/) (adapt dbt-core to confluent cloud) and [`confluent-sql`](https://pypi.org/project/confluent-sql/) (Python DBAPI V2 Compatible driver to be able to run snapshot, streaming queries with different cursors). 

![](./diagrams/dbt_cc.drawio.png)

All the flink statements presented in this repository are deployed using Confluent dbt. The project management is also complemented with other personal CLIs. 

[See this note](./flink_deployment.md) to review the development approach and deployment pattern using dbt for this solution.

[See Confluent dbt product documentation.](https://docs.confluent.io/cloud/current/flink/operate-and-deploy/deploy-flink-dbt.html)

### Lateral snapshot join on slow moving, seeded data

One of common pattern within data enrichment is to join streaming record with reference data, which has lower level of change velocity. There are multiple way to support this integration, but in Confluent Cloud is it best to deploy them in Kafka topic and be able to reuse them, for any enrichment. The [new lateral snapshot feature in Flink](https://docs.confluent.io/cloud/current/flink/reference/queries/joins.html#lateral-snapshot-joins) helps in join.

The seeds are defined is pipelines/seeds folder and deployed simply by doing
```sh
dbt seed
```

* [seeds/country_codes.csv](https://github.com/jbcodeforce/streamhouse_c360_demo/blob/main/pipelines/seeds/country_codes.csv) has 249 ISO 3166-1 countries with alpha-2, alpha-3, numeric code and name. The country_code key matches customers.country.
* [seeds/currency_codes.csv](https://github.com/jbcodeforce/streamhouse_c360_demo/blob/main/pipelines/seeds/currency_codes.csv) has 178 ISO 4217 currencies with code, numeric code and name. The currency_code key matches transactions.currency.
* [seeds/seeds.yml](https://github.com/jbcodeforce/streamhouse_c360_demo/blob/main/pipelines/seeds/seeds.yml) adds descriptions, plus unique and not_null tests on the two key columns

The snaphot lateral join query is implemented in the [transaction cdc processing]()

### Snapshot query

dbt supports running materialized table and streaming tables. The Confluent REST API exposes a run Flink statement that can also being used for snapshot query. The backend application uses the [confluent sql](https://pypi.org/project/confluent-sql/) module to demonstrate the integration inside of a human dashboard. 

[See this confluent client code](https://github.com/jbcodeforce/streamhouse_c360_demo/blob/main/apps/backend/analytics/confluent_sql_client.py#L51).

### Lightning query

The Confluent Cloud [Real-Time Context Engine]() (RTCE) exposes a Flink-maintained table for current-state point lookups over HTTP: a single synchronous POST returns the
table's current rows in milliseconds. 

The request is HTTP Basic auth with a dedicated *Global* resource API key (``CONFLUENT_GLOBAL_KEY``/``SECRET``,
provisioned by ``IaC/ccloud/lightning.tf``) and a body scoped by ``catalog_name`` = environment *id* and ``database_name`` = Kafka cluster *id* (IDs, not the display names the Flink SQL Statements API uses).

See [Code reference](https://github.com/jbcodeforce/streamhouse_c360_demo/blob/main/apps/backend/analytics/lightning_client.py)

### Complex event processing for fraud detection
### Chat with business data leveraging real-time context engine

The Frontend exposes a panel with a chat interface to demonstrate calling local LLM with tool to reference Confluent Real-time context engine to query data exposed with Lightning tables.

![](./diagrams/chat_rtce.drawio.png)

### Flink pipeline lineage
### Billing aggr
### Others to finalize
* [ ] Sliding window aggregations over transactions grouped by cardholder (1 minute to 1 day windows). 
* [ ] How to propagate delete operations to sink bucket
* [ ] Maintain data order for transactional systems. 
* [ ] Iceberg table and tableflow enabled in dbt
* [ ] Tableflow Catalog in sync with AWS Glue Catalog
* [ ] AWS Athena integrated with AWS Glue Catalog for the Kafka Cluster defined and then being able to see and query the Iceberg tables. 
* [ ] What monitoring and observability requirements exist? 

### Architecture

As a generic application behaviors:

* Microservice applications write to database tables.
* PostgreSQL database server
* CDC Debezium Kafka Connector, create one topic per table, define schema in schema registry
* A set of Flink queries prepare the data to build customer 360 analytics metrics, that are served in sink topics
* Sink topic is processed by Tableflow to export data as Iceberg table / parquet files into object storage
* External catalogs are in sync with Tableflow catalog
* Web Application to support demonstrating Streamhouse capabilities

Two architectures are presented in this repository, one pure cloud, and one hybrid with local server, database, CDC to Confluent cloud Kafka cluster and Streamhouse:

=== "Hybrid cloud"

    This is the simplest deployment to run database and code locally with Confluent Cloud for Kafka, Flink, Tableflow and Streamhouse components.

    <figure markdown='span'>
    ![](./diagrams/app/stream-cut1-local-arch.drawio.png)
    <caption>Local Database - Confluent Cloud Streamhouse</caption>
    </figure>

    * The postgresql server runs locally via container (on Mac - docker compose on Windows. (not yet supported)).
    * A Kakfa connector Debezium container image runs locally to CDC the 3 tables to the `cdc.public.*` topics
    * WebApp runs locally

    The WebApp adds simple navigation, to create, update, delete customers and accounts. Transactions are creation only.

    <figure markdown='span'>
    ![](./images/app/customers.png)
    <caption>Application Customers Page</caption>
    </figure>

=== "Cloud VPV to VPC"
    The end-to-end, more complex architecture, looks like in the following figure:

    <figure markdown='span'>
    ![](./diagrams/app/stream-cut1-arch.drawio.png)
    <caption>Cloud Deployment - Confluent Cloud Streamhouse</caption>
    </figure>

    * Application runs on EC2 host
    * PostgreSQL database server on AWS RDS
    * CDC Debezium Kafka Connector deployed as managed service
    * Kafka cluster, schema registry, real-time context engine, tableflow and Flink jobs run on Confluent Cloud

    ! Being more complex to deploy, this is still under construction and testing.


#### Web app backend Architecture

The Web App and backend to support running the demonstration has the following components:

<figure markdown='span'>
![](./diagrams/app/backend.drawio.png)
<caption>Application High Level Component View</caption>
</figure>

* This is to emulate a microservice implementation where each service is responsible for its own business entity life cycle. An evolution of the implementation will be to implement the [CQRS pattern](https://jbcodeforce.github.io/eda-studies/patterns/cqrs/), and deploy each component as a standalone application
* [See implementation details for developers willing to update this demonstration](./web_app_design.md)


---

## Actors

The Streamhouse architecture offers services for three different actors:

1. Site Reliability Engineer
1. Data Engineer
1. Application Developer

### SRE

This use case helps to demonstrate the following tasks a SRE needs to conduct to prepare the environment to support the above architecture. 

There are two ways to execute those tasks, via Confluent Cloud Console or via infrastructure as Code, using Terraform. The following bullet points are generic task description that should be done using both approaches, (some are for production deployment too). 

1. Create Confluent Cloud environment, API keys and secrets, service accounts, role bindings, kakfa cluster
1. For Production deployment create private network and network link to Confluent cloud 
1. A Schema Registry for a given environment
1. Create Flink compute pool
1. Create source databases, for example, a RDS service with a Postgresql instance  
1. Create Debezium CDC Source connector for DB tables using terraform
1. Create SQL database and tables into the select database (Postgresql): accounts, customers, transactions.

*This list will be updated while implementing this demonstration*

### Data Engineer

The following steps are generic and may be supported by different tools:

1. Create dbt project to manage Flink statements using a git repository. One of the approach is to use the `star schema` (see note below)
1. Develop Flink queries using Confluent Cloud Workspace cells
1. Save query to file in git repository, transform for dbt
1. Deploy Flink logic using dbt cli: `dbt run`

*This list will be updated while implementing this demonstration*

We recommend organizing the Flink statements using the [**Star model**](http://jbcodeforce.github.io/flink-studies/cookbook/pm/?h=star+model#the-star-schema) which is a multidimensional data model to organize data in a data warehouse. It is used to denormalize business data into dimensions and facts. The `fact` table sits at the center of the star schema. It records the `what` happened, as quantitative, measurable events. The `Dimension` tables (The "Context") surround the fact table. They provide the "who, what, where, when, and why".

### Application Developer

The following steps are generic and may be supported by different tools:

1. Define contract for data / analytics, and the methodology to engage with Data engineers as part of the microservice design
1. Maintain schema evolution with full transitivity
1. Integrate data in Kafka via Lightning query or snapshot queries.

*This list will be updated while implementing this demonstration*

* The WebApp delivered as a MVP illustrates the integration with those new query capability to serve the data to application.

--- 

## Sources for information

* [My living Flink study book](https://jbcodeforce.github.io/flink-studies/) with best practices, methodology, and code samples.
* [Confluent Stream Processing with Confluent Cloud for Apache Flink](https://docs.confluent.io/cloud/current/flink/overview.html)
* [Streamhouse](https://streamhouse.com/) web site
