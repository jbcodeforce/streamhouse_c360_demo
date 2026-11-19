# Defining Confluent Cloud Resources with Terraform

This section presents the steps to deploy the Confluent Cloud components for Streamhouse using Terraform.

Terraform is organized under the [`IaC/`](https://github.com/jbcodeforce/streamhouse_c360_demo/tree/main/IaC) directory as **independent root modules** (separate local state), each file-per-concern:

| Module | Wrapper script | Purpose | When |
|--------|----------------|---------|------|
| [`IaC/ccloud`](https://github.com/jbcodeforce/streamhouse_c360_demo/tree/main/IaC/ccloud) | none (run `terraform` directly) | Core Confluent Cloud: environment, Kafka cluster, Flink compute pools, Schema Registry API key, service accounts, Kafka/Flink API keys, topics. Needs **no AWS credentials**. | Always, first |
| [`IaC/rtce`](https://github.com/jbcodeforce/streamhouse_c360_demo/tree/main/IaC/rtce) | none (run `terraform` directly) | **Real-Time Context Engine / Lightning Query API**: Global API key and registration of `fct_c360_profile` and `fct_crm_summary` as RTCE topics. | After `dbt run` |
| [`IaC/AWS`](https://github.com/jbcodeforce/streamhouse_c360_demo/tree/main/IaC/AWS) | [`scripts/tf_aws.sh`](https://github.com/jbcodeforce/streamhouse_c360_demo/blob/main/scripts/tf_aws.sh) | PostgreSQL RDS 17 (CDC-ready), security group, KMS, Secrets Manager secret. | Opt-in (cost) |
| [`IaC/connector`](https://github.com/jbcodeforce/streamhouse_c360_demo/tree/main/IaC/connector) | [`scripts/tf_connector.sh`](https://github.com/jbcodeforce/streamhouse_c360_demo/blob/main/scripts/tf_connector.sh) | Managed Debezium PostgreSQL CDC source connector. Reads `IaC/ccloud` state and the RDS secret. | Opt-in (cost) |
| [`IaC/EC2`](https://github.com/jbcodeforce/streamhouse_c360_demo/tree/main/IaC/EC2) | [`scripts/tf_ec2.sh`](https://github.com/jbcodeforce/streamhouse_c360_demo/blob/main/scripts/tf_ec2.sh) | EC2 app host for the backend and frontend containers. Reads `IaC/AWS` state. | Opt-in |

This split lets the core Confluent Cloud stack run locally with no AWS credentials. AWS, the managed connector and the app host are opt-in cost paths. For a CDC path with no AWS at all, see [Local CDC](local_cdc.md).

**Apply order:** `IaC/ccloud` → `dbt run` → `IaC/rtce`. Add `IaC/AWS` → `IaC/connector` for the managed CDC path, and `IaC/EC2` to host the apps.

The figure below illustrates what the Terraform in [`IaC/ccloud/`](https://github.com/jbcodeforce/streamhouse_c360_demo/tree/main/IaC/ccloud) deploys. We start from an existing Organization, a user or service account with the Org Admin role, and a Confluent Cloud Resource API key and secret.

![](./diagrams/cc-tf-comp.drawio.png)

## What `IaC/ccloud` creates

| File | Resources |
|------|-----------|
| `provider.tf` | Requires only the `confluentinc/confluent` provider (`~> 2.88.0`). |
| `env.tf` | Environment `${prefix}-env` with the `ESSENTIALS` stream governance package. This auto-provisions Schema Registry. |
| `kafka.tf` | Standard, single-zone Kafka cluster `${prefix}-kafka`. Service account `${prefix}-kafka-mgr` with `CloudClusterAdmin` on the cluster, and its Kafka API key. |
| `flink.tf` | Three Flink compute pools: `${prefix}-flink-pool` (c360), `${prefix}-crm-flink-pool` (crm) and `${prefix}-snapshot-q-pool` (snapshot queries). Service account `${prefix}-flink-runner` with `EnvironmentAdmin` and `Assigner` (on itself), and the environment/region-scoped Flink API key. Optional Cost API billing role binding. No Flink statements: dbt deploys them. |
| `schema_registry.tf` | Looks up the environment's Schema Registry and creates its API key, owned by the existing `cc_sa_env_mgr` service account (read in `data.tf`). |
| `topics.tf` | Topic `agent_conversations` (chat request/response events) and the Kafka Connect storage topics `my_connect_configs`, `my_connect_offsets` and `my_connect_status` (compacted). |
| `variables.tf` | Inputs. See below. |
| `outputs.tf` | Values consumed by [`scripts/set_env_from_tf.sh`](https://github.com/jbcodeforce/streamhouse_c360_demo/blob/main/scripts/set_env_from_tf.sh) to build the application environment. |

The compute pool `max_cfu` is set by `flink_max_cfu` (c360) and `flink_crm_max_cfu` (crm and snapshot pools, default 50 each).

### Outputs

`environment_id`, `env_display_name`, `cc_region`, `cloud_provider`, `kafka_id`, `kafka_name`, `kafka_bootstrap_endpoint`, `kafka_rest_endpoint`, `kafka_api_key_id` / `_secret`, `sa_id`, `sa_name`, `flink_compute_pool_id`, `flink_crm_compute_pool_id`, `flink_sn_compute_pool_id`, `flink_runner_sa_id`, `flink_api_key_id` / `_secret`, `schema_registry_id`, `schema_registry_rest_endpoint`, `schema_registry_api_key_id` / `_secret`, plus `agent_conversations_topic` and `debezium_topics`.

## What `IaC/rtce` creates

The module reads the environment and cluster ids from `../ccloud/terraform.tfstate` through `terraform_remote_state` (same pattern as `IaC/connector`). Data sources expose the cluster `rbac_crn` and the Schema Registry `resource_name` for the role bindings.

- `rtce.tf`:
    - service account `${prefix}-rtce-lightning`;
    - role bindings: `CloudClusterAdmin` on the Kafka cluster and `ResourceOwner` on all Schema Registry subjects;
    - the **Global API key** (`managed_resource` kind `Global`);
    - `confluent_rtce_topic.fct_c360_profile` and `confluent_rtce_topic.fct_crm_summary`, which register those existing topics with RTCE so the Lightning Query API serves them. Add more `confluent_rtce_topic` resources to expose other fact or dimension tables.
- `outputs.tf`: `rtce_lightning_sa_id`, `rtce_lightning_api_key_id` / `_secret` (used for `CONFLUENT_GLOBAL_KEY` / `CONFLUENT_GLOBAL_SECRET`), `rtce_c360_profile_topic_name`, `rtce_crm_summary_topic_name`.

## Pre-requisites

* [git cli](https://git-scm.com/install/)
* [Terraform cli](https://developer.hashicorp.com/terraform/tutorials/aws-get-started/install-cli) (the modules declare `required_version >= 1.16.3`)
* Clone this repository:
    ```sh
    git clone https://github.com/jbcodeforce/streamhouse_c360_demo.git
    cd streamhouse_c360_demo
    ```

## Get Confluent Cloud environment information

* Log in to the Confluent Console.
* Get your user identifier if you are an organization admin, or ask your Organization administrator for a service account that has the Org Admin role. A user id starts with `u-`, a service account id with `sa-`. This id is the `cc_sa_env_mgr` value below.

    A service account is recommended.

    ![](./images/ccloud/sa-id.png)

    Verify that this service account has the Org Admin role binding:

    ![](./images/ccloud/role_bdg-org_admin.png)
* Get the API key and secret for Cloud resource management, or create a new one:

    ![](./images/ccloud/cc-apikey.png)
* Export the key and secret as environment variables in a fresh terminal session. They are the only Confluent Cloud credentials you provide. Everything else (ids, Kafka, Flink and Schema Registry keys) comes from the Terraform outputs:
    ```sh
    export CONFLUENT_CLOUD_API_KEY=PQ...
    export CONFLUENT_CLOUD_API_SECRET=cflt....
    ```
* In `IaC/ccloud/`, copy `terraform.tfvars.example` to `terraform.tfvars` and fill in the values:
    ```sh
    cp IaC/ccloud/terraform.tfvars.example IaC/ccloud/terraform.tfvars
    ```

    | Variable | Default | Description |
    |----------|---------|-------------|
    | `cc_sa_env_mgr` | required | Existing service account (`sa-...`) that owns the Schema Registry API key. |
    | `prefix` | `j9r-jtbd1` | Prefix for all resource names. |
    | `cloud_provider` | `AWS` | Cloud of the Kafka cluster and Flink pools. |
    | `aws_region_primary` | `us-west-2` | Region of the Kafka cluster and Flink pools. |
    | `flink_max_cfu` / `flink_crm_max_cfu` | `50` / `50` | Max CFUs per compute pool. |
    | `cost_api_principal_id` | `null` | Principal (`sa-...` / `u-...`) behind `CONFLUENT_CLOUD_API_KEY`. When set, it gets `cost_api_billing_role` (default `OrganizationAdmin`) so the backend Cost API can read billing data. Leave it unset if that principal is already Org Admin. |
    | `agent_conversations_topic` / `_partitions` | `agent_conversations` / `6` | Chat history topic. |

    The example file contains `cost_api_principal_id =` with no value. Set a value or comment the line out before running Terraform.

    Do NOT commit `terraform.tfvars`. It is gitignored in this repo.

## Perform the deployment

Run the commands below from the `IaC/ccloud` folder:

```sh
cd IaC/ccloud
```

* Initialize Terraform:
    ```sh
    terraform init
    ```

* Run the plan to assess what will be created:
    ```sh
    terraform plan
    ```

* Deploy the resources:
    ```sh
    terraform apply
    ```

    Some resources may take time to create.

* The outputs are printed at the end. You can retrieve them at any time with:
    ```sh
    terraform output
    ```

* Validate in the Confluent Console that the resources are created:

    ![](./images/ccloud/cc-resources.png)

* Write the API keys and ids into `apps/backend/.env`:
    ```sh
    cd ../..   # repo root
    ./scripts/set_env_from_tf.sh
    ```

    This reads the outputs of `IaC/ccloud` and updates `apps/backend/.env`, created from `.env.example` if missing. The variables written are:

    | Source | Variables |
    |--------|-----------|
    | `IaC/ccloud` | `ENVIRONMENT_ID`, `FLINK_ENV_ID`, `CLOUD_REGION`, `CLOUD_PROVIDER`, `KAFKA_CLUSTER_ID`, `KAFKA_CLUSTER_NAME`, `KAFKA_BOOTSTRAP_SERVERS`, `KAFKA_API_KEY` / `_SECRET` |
    | `IaC/ccloud` (Flink) | `FLINK_COMPUTE_POOL_ID`, `FLINK_CRM_COMPUTE_POOL_ID`, `FLINK_SNAPSHOT_COMPUTE_POOL_ID`, `FLINK_API_KEY` / `_SECRET`, `FLINK_REST_ENDPOINT`, `FLINK_CATALOG` (environment display name), `FLINK_DATABASE` (Kafka cluster name) |
    | `IaC/ccloud` (Schema Registry) | `SCHEMA_REGISTRY_URL`, `SCHEMA_REGISTRY_API_KEY` / `_SECRET` |
    | `IaC/rtce` | `CONFLUENT_GLOBAL_KEY` / `_SECRET`. Empty until that stack is applied (see below). |
    | `IaC/AWS` (if applied) | `DATABASE_URL`, built from the RDS outputs and the password in Secrets Manager. Needs the AWS CLI and `jq`. Otherwise the existing database settings are kept. |

    Run `source scripts/set_env_from_tf.sh` instead to also export the variables into your current shell.

## dbt

`dbt run` can be applied in a CI/CD process with a SHA guard to avoid redeploying materialized tables that were not modified. The dbt project is in [`pipelines/`](https://github.com/jbcodeforce/streamhouse_c360_demo/tree/main/pipelines). Set the environment variables first:

```sh
set -a
source apps/backend/.env
set +a
```

The current lineage is presented by running:

```sh
cd pipelines
dbt docs generate
dbt docs serve
```

![](./images/dbt_lineage_graph.png)

The green topics are created by applications or the CDC connector.

The command below deploys to the target environment:

```sh
dbt run --select +c360.facts.fct_c360_profile
```

This creates all the topics in the Kafka cluster:

![](./images/LT_in_topic.png)
**Topics created by dbt**

## Enable the Real-Time Context Engine (RTCE / Lightning Query API)

The analytics "Customer lookup via RTCE" section queries `fct_c360_profile` through Confluent's **Lightning Query API**, a current-state point-lookup serving layer. Enabling it is a separate stack (`IaC/rtce`) because it must run **after** the tables exist.

**Order of operations:**

1. `IaC/ccloud` applied (previous sections): environment and Kafka cluster.
2. `dbt run`: creates the `fct_c360_profile` and `fct_crm_summary` upsert/compacted topics.
3. `IaC/rtce` applied: Global key, and registration of the topics with RTCE.

**Prerequisites:**

* The **Real-Time Context Engine / Lightning Query API Early Access** feature must be enabled for your Confluent **organization**. Without it the Lightning API reports the org as not found (HTTP 400) regardless of this stack.
* An **OrganizationAdmin** Cloud API key for the Terraform provider. Creating a service account, a Global API key and an RTCE topic are org-level operations, and a resource-scoped key returns 401. Provide it as `CONFLUENT_CLOUD_API_KEY` / `CONFLUENT_CLOUD_API_SECRET`, or as `confluent_cloud_api_key` / `confluent_cloud_api_secret` in `terraform.tfvars`.
* The topics named by `profile_topic` (`fct_c360_profile`) and `crm_summary_topic` (`fct_crm_summary`) already exist (step 2 done).
* The `IaC/ccloud` state at `core_state_path` (default `../ccloud/terraform.tfstate`).

**Deploy:**

```sh
cd IaC/rtce
cp terraform.tfvars.example terraform.tfvars   # set prefix / cloud / region to match IaC/ccloud
terraform init
terraform apply
```

The same `CONFLUENT_CLOUD_API_KEY` / `CONFLUENT_CLOUD_API_SECRET` variables are used. There is no wrapper script for this module.

This creates a dedicated service account, grants it `CloudClusterAdmin` on the cluster and `ResourceOwner` on the Schema Registry subjects, creates the **Global API key**, and registers the two topics with RTCE through `confluent_rtce_topic`.

**Wire the key into the backend:**

```sh
cd ../..                      # repo root
./scripts/set_env_from_tf.sh  # now picks up CONFLUENT_GLOBAL_KEY / _SECRET from IaC/rtce
```

The Lightning query is scoped by `catalog_name` = environment **id** (`FLINK_ENV_ID`) and `database_name` = Kafka cluster **id** (`KAFKA_CLUSTER_ID`). These are ids, not the display names the Flink SQL Statements API uses. Restart the backend so it reloads `apps/backend/.env`. The RTCE customer lookup then serves results.

## Optional modules

These need AWS credentials. Each wrapper refreshes the AWS SSO token if needed and exports temporary credentials for the profile in `AWS_PROFILE` (default `default`). `tf_aws.sh` and `tf_ec2.sh` also check that the profile resolves to the expected account (`EXPECTED_AWS_ACCOUNT_ID`; set it empty to skip).

```sh
# RDS PostgreSQL + Secrets Manager (needs CONFLUENT_CLOUD_API_KEY/SECRET exported)
./scripts/tf_aws.sh apply

# Managed Debezium CDC connector (needs IaC/ccloud and IaC/AWS applied first)
./scripts/tf_connector.sh apply

# App host (needs IaC/AWS applied first; copy terraform.tfvars.example first)
./scripts/tf_ec2.sh apply
```

For a local PostgreSQL and Debezium instead of these modules, see [Local CDC](local_cdc.md).
