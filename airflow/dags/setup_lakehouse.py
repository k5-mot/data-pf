# [要件] AirflowのDAG
# 1. yfinanceで株価データを取得
# 2. Delta Lake形式でMinIOのブロンズレイヤに保存する

from airflow import DAG
from airflow.providers.apache.spark.operators.spark_submit import SparkSubmitOperator
from datetime import datetime

default_args = {
    'owner': 'airflow',
    'start_date': datetime(2025, 7, 26),
}

with DAG('ingest_yfinance_to_delta',
         default_args=default_args,
         schedule=None,
         catchup=False) as dag:

    ingest_yfinance = SparkSubmitOperator(
        task_id='ingest_yfinance',
        application="/opt/airflow/scripts/create_schema.py",
        conn_id="spark_default",
        deploy_mode="client",
        # jars="/opt/airflow/jars/aws-java-sdk-bundle-1.12.367.jar,/opt/airflow/jars/delta-spark_2.12-3.3.2.jar,/opt/airflow/jars/delta-storage-3.3.2.jar,/opt/airflow/jars/hadoop-aws-3.2.3.jar,/opt/airflow/jars/mysql-connector-java-8.0.19.jar,/opt/airflow/jars/delta-hive_2.12-3.3.2.jar",
        # conf={
        #     "spark.sql.extensions": "io.delta.sql.DeltaSparkSessionExtension",
        #     "spark.sql.catalog.spark_catalog": "org.apache.spark.sql.delta.catalog.DeltaCatalog",
        #     "spark.hadoop.fs.s3a.endpoint": "http://minio:9000",
        #     "spark.hadoop.fs.s3a.access.key": "admin",
        #     "spark.hadoop.fs.s3a.secret.key": "adminpass",
        #     "spark.hadoop.fs.s3a.impl": "org.apache.hadoop.fs.s3a.S3AFileSystem",
        #     "spark.hadoop.fs.s3a.path.style.access": "true",
        #     "spark.hadoop.fs.s3a.connection.ssl.enabled": "false",
        #     "spark.hadoop.fs.s3a.aws.credentials.provider": "org.apache.hadoop.fs.s3a.SimpleAWSCredentialsProvider",
        #     "spark.sql.warehouse.dir": "s3a://lakehouse/",
        #     "hive.metastore.uris": "thrift://hive-metastore:9083"
        # }
    )

    ingest_yfinance
