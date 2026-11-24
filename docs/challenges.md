# Challenges

!!! info "Version"
    **Last updated:** 2026-11-24

## RDS out of storage - connection from client rejected

When an AWS RDS PostgreSQL instance reaches a storage-full state, AWS restricts database access and rejects standard client connections to prevent corruption.

Even without new application data being inserted, PostgreSQL can rapidly fill disk space through Write-Ahead Logging (WAL) retention, abandoned replication slots, verbose error logging, or orphaned temp files.

* Need to scale up storage, max storage limit and current storage by +20%.
* Connect with psql (be sure your public IP address is in the security group policy as inbound rules on port 5432)
    ```sh
    export RDSHOST="c360-j9r-postgres.c......rds.amazonaws.com" 
    psql "host=$RDSHOST port=5432 dbname=c360db user=dbadmin sslmode=verify-full sslrootcert=~/.ssh/global-bundle.pem"
    ```

* Identify why storage growth occurred. Once connected via psql or your SQL client, run the following diagnostic checks. First, check for abandoned or inactive replication slots (most common cause): if you have an inactive read replica or a disconnected CDC tool (AWS DMS, Debezium, Kafka), PostgreSQL will indefinitely hold Write-Ahead Logs (WAL) on disk waiting for the consumer to catch up.
    ```sql
    SELECT slot_name, plugin, active, 
        pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)) AS wal_lag
    FROM pg_replication_slots;
    ```

* If a slot has active = false and high wal_lag, drop the slot to immediately clear accumulated WAL files:
    ```sh
    SELECT pg_drop_replication_slot('your_slot_name');
    ```

* Check for long-running or stuck transactions: Uncommitted or long-running transactions prevent PostgreSQL from vacuuming dead tuples and clearing old WAL files.
    ```sql
    SELECT pid, age(clock_timestamp(), query_start), usename, state, query 
    FROM pg_stat_activity 
    WHERE state != 'idle' 
    ORDER BY query_start ASC;
    ```

* Inspect RDS log file accumulation: Verbose error logging (e.g., repeated connection failure loops or heavy query logging) can generate tens of gigabytes of text log files on the host. Go to RDS Console > Databases > [Your Instance] > Logs & events.
    * If log files are taking up massive space, check your DB Parameter Group and adjust `rds.log_retention_period` to a shorter duration (e.g., 1440 minutes / 1 day).  
    * `log_min_duration_statement`: Increase this value (e.g., 5000 for 5 seconds) or set it to -1 to disable slow query logging entirely.   
    * `log_statement`: Change to none or ddl (avoid all)
    * `log_min_messages`: Set to warning or error (avoid info or debug).
    * `log_parameter_max_length`: Reduce this value (e.g., 1024) to cap the size of logged query bind parameters

* Check for file bloat: complex queries (e.g., large sorts or joins exceeding `work_mem`) create temp files on disk. Aborted operations can sometimes leave orphaned temp files.
    ```sql
    SELECT datname, temp_files, pg_size_pretty(temp_bytes) AS temp_size 
    FROM pg_stat_database;
    ```
