# Defining Confluent Cloud Resources with the Console

!!! info "Version"
    **Last updated:** 2026-11-24

## SRE's tasks Walking Through

### Confluent Console Walk Through

We assume the user has the `OrganizationAdmin` role to be able to create an environment.

Pre-requisites:

* Login to the Confluent Cloud console

#### Create Confluent Cloud Environment

1. From the home page, go to the environment page, and click on the `Add Cloud Environment` button on the top right part of the page.
1. Enter a name and select one of the governance packages. As the demonstration scope is not about governance, use **Essentials**.

    ![](./images/ccloud/cc-env-1.png)

#### Create Confluent Cloud Kafka Cluster

The next step is to create a Kafka cluster.
1. Enter name, and Cluster Type, which for demonstration will be standard.

    ![](./images/ccloud/cc-kafka-1.png)
1. Select a Cloud Provider and a region, select a 99.9% SLA
1. Launch the cluster using the right column 'Launch Cluster button`
1. Create API Key and Secrets

*As part of the essential governance, a schema registry is created once the Kafka Cluster is launched.*

#### Create Confluent Cloud Flink Compute Pool


#### Create Debezium CDC v2 Kafka Connector

Once the database instance is created and has DNS server name and port number and access policies setup, we need to add the Kafka Connector. The figure below illustrates the components created:

![](./diagrams/kafka-connect.drawio.png)

[See confluent Cloud product documentation](https://docs.confluent.io/cloud/current/connectors/cc-postgresql-cdc-source-v2-debezium/cc-postgresql-cdc-source-v2-debezium.html)


1. Select the Kafka Cluster
    ![](./images/ccloud/cc-cdc-1.png)

1. Select Connector Tab to land in the connectors home page:
    ![](./images/ccloud/cc-cdc-2.png)

1. Add Connector, and select the Postgres CDC Source V2
    ![](./images/ccloud/cc-cdc-deb.png)

1. Add topic information such as the prefix to use to differentiate among other topics. Set the default number of partitions and the cleanup policy.

    ![](./images/ccloud/cdc-topic-cfg.png)

1. Define how to access the Kafka cluster. Use an existing API Key ...

    ![](./images/ccloud/cdc-kafka-access.png)

    or create a new one

    ![](./images/ccloud/cdc-kafka-access-2.png)


1. Define connection credentials to external database
    ![](./images/ccloud/cc-cdc-auth.png)


1. Define topic configuration
    ![](./images/ccloud/cdc-sr-avro.png)

1. Launch the connector
1. Verify created topics
    ![](./images/ccloud/kafka-topics.png)

1. Verify Schema registry schemas
    ![](./images/ccloud/cdc-schemas.png)

