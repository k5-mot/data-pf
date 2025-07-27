#!/usr/bin/env python3
import os
from pyspark.sql import SparkSession
from datetime import date
import sys

sys.path.append('/opt/airflow/scripts')
from common.spark_session import get_spark_session


def main():
    # When using SparkSubmitOperator, SparkSession is already configured
    # by the cluster with the jars and conf from the DAG
    # spark = SparkSession.builder.getOrCreate()
    spark = get_spark_session(SparkSession)

    spark.sql(f"CREATE SCHEMA IF NOT EXISTS bronze")
    spark.sql(f"CREATE SCHEMA IF NOT EXISTS silver")
    spark.sql(f"CREATE SCHEMA IF NOT EXISTS gold")
    spark.sql(f"CREATE SCHEMA IF NOT EXISTS feature_store")
    spark.sql("SHOW DATABASES").show()


if __name__ == "__main__":
    main()
