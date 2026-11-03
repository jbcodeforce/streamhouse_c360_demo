
## Purpose

The purpose of this repo is to implement a Customer 360 streaming data pipeline integrating operational databases (PostgreSQL, DB2,...) with event streaming, Change Data Capture (CDC), and modern lakehouse analytical sinks. 

<figure markdown='span'>
![](./images/app/home_page.png)
<caption>**The home page of the application to drive the demonstration**</caption>
</figure>

It is a demonstration of the [Streamhouse architecture](https://streamhouse.com) with Confluent Cloud solution.

The user story for the demonstration looks like: 

> as a data architect I want to deliver the business entities update to every system and person that depends on it, at the same time, so I can ensure no team operates on a **stale or conflicting copy** of that fact.

Streamhouse data architecture continuously captures and processes changes as they happen, governs that data, and makes the same trusted business context available to applications, agents and analytics without requiring another set of data copies and pipelines.

At the high level, Streamhouse reference architecture looks like in the figure below:

<figure markdown='span'>
![](./diagrams/stream-arch.drawio.png)
<caption>Streamhouse Capabilities</caption>
</figure>

The architecture delivers a capture layer to bring data in centralized messaging platform to transport and persist records defined in structured schemas. A layer of tranformation, data enrichment and data analytics construct helps to serve golden records to downstream processing. Those golden records, representing valuable business events or data analytic products can be consumed by AI Agent to build their own, fresh, context.

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

## Goal of this demonstration

**The goal is to demonstrate how to synchronize a change in business state everywhere it is used.**

We will mockup transactional application / microservices writing transactions, accounts and customers records to a SQL database. We can use IBM Db2 RDBMS or Postgresql as databasse server. The solution can run the database server locally or remotely deployed on AWS RDS. 

The end-to-end, more complex architecture, looks like in the following figure:

<figure markdown='span'>
![](./diagrams/app/stream-cut1-arch.drawio.png)
<caption>Remote Database - Confluent Cloud Streamhouse</caption>
</figure>


* Microservice applications write to database tables.
* PostgreSQL database server on AWS RDS
* CDC Debezium Kafka Connector, create one topic per table, define schema in schema registry
* A set of Flink queries will prepare the data to build customer 360 analytics metrics, that will be served in a sink topic
* Sink topic is processed by Tableflow to export data as Iceberg table / parquet files into object storage
* External catalogs are in sync with Tableflow catalog
* Other queries are done by Data engineer on data at rest.
* Web Application for demonstration (run locally as of now)

There is a simpler architecture to run database and code locally with Confluent Cloud for Kafka, Flink, Tableflow and Streamhouse components.

<figure markdown='span'>
![](./diagrams/app/stream-cut1-local-arch.drawio.png)
<caption>Local Database - Confluent Cloud Streamhouse</caption>
</figure>

The differences with the more complex architecture, are:

* the postgresql server runs locally via container (on Mac - docker compose on Windows. (not yet supported)).
* The application writes directly to `cdc.public.*` topics as Debezium will do
* WebApp runs locally

The WebApp adds simple navigation, to create, update, delete customers and accounts. Transactions are creation only.

<figure markdown='span'>
![](./images/app/home_page.png)
<caption>Application Home Page</caption>
</figure>


### Web app backend Architecture

The Web App and backend to support running the demonstration has the following components:

<figure markdown='span'>
![](./diagrams/app/backend.drawio.png)
<caption>Application High Level Component View</caption>
</figure>

* This is to emulate a microservice implementation where each service is responsible for its own business entity life cycle. An evolution of the implementation will be to implement the [CQRS pattern](https://jbcodeforce.github.io/eda-studies/patterns/cqrs/), and deploy each component as a standalone application
* [See implementation details for developers willing to update this demonstration](./web_app_design.md)

### Capabilities demonstrated

#### CDC envelop automatic processing to upsert tables

#### DBT deployment, Materialized and Streaming tables

#### Lateral snapshot join on slow moving data
#### Snapshot query
#### Lightning query
#### Complex event processing for fraud detection
#### Chat with business data leveraging real-time context engine
#### Flink pipeline lineage
#### Billing aggregation per pipeline


## Sources

* [My living Flink study book](https://jbcodeforce.github.io/flink-studies/)
* [Confluent Stream Processing with Confluent Cloud for Apache Flink](https://docs.confluent.io/cloud/current/flink/overview.html)
* [Streamhouse](https://streamhouse.com/)
