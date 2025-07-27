import os

AWS_ACCESS_KEY = os.getenv('AWS_ACCESS_KEY', 'admin')
AWS_SECRET_KEY = os.getenv('AWS_SECRET_KEY','adminpass')
AWS_S3_ENDPOINT = os.getenv('AWS_S3_ENDPOINT', 'http://minio:9000')
AWS_BUCKET_NAME = 'lakehouse'


def get_spark_session(spark_session):

    spark = spark_session.builder \
        .appName('Ingest checkin table into bronze') \
        .master('spark://spark-master:7077') \
        .config("hive.metastore.uris", "thrift://hive-metastore:9083")\
        .config("spark.hadoop.fs.s3a.access.key", AWS_ACCESS_KEY) \
        .config("spark.hadoop.fs.s3a.secret.key", AWS_SECRET_KEY) \
        .config("spark.hadoop.fs.s3a.endpoint", AWS_S3_ENDPOINT)\
        .config("spark.hadoop.fs.s3a.path.style.access", "true")\
        .config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem") \
        .config("spark.hadoop.fs.s3a.connection.ssl.enabled", "false")\
        .config('spark.hadoop.fs.s3a.aws.credentials.provider', 'org.apache.hadoop.fs.s3a.SimpleAWSCredentialsProvider')\
        .config('spark.sql.warehouse.dir', f's3a://{AWS_BUCKET_NAME}/')\
        .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension") \
        .config("spark.sql.catalog.spark_catalog", "org.apache.spark.sql.delta.catalog.DeltaCatalog")\
        .config('spark.jars', '/opt/airflow/jars/aws-java-sdk-bundle-1.12.367.jar,/opt/airflow/jars/delta-spark_2.12-3.3.2.jar,/opt/airflow/jars/delta-storage-3.3.2.jar,/opt/airflow/jars/hadoop-aws-3.2.3.jar,/opt/airflow/jars/mysql-connector-java-8.0.19.jar,/opt/airflow/jars/delta-hive_2.12-3.3.2.jar')\
        .config('spark.driver.extraClassPath', '/opt/airflow/jars/aws-java-sdk-bundle-1.12.367.jar:/opt/airflow/jars/delta-spark_2.12-3.3.2.jar:/opt/airflow/jars/delta-storage-3.3.2.jar:/opt/airflow/jars/hadoop-aws-3.2.3.jar:/opt/airflow/jars/mysql-connector-java-8.0.19.jar:/opt/airflow/jars/delta-hive_2.12-3.3.2.jar')\
        .config('spark.executor.extraClassPath', '/opt/airflow/jars/aws-java-sdk-bundle-1.12.367.jar:/opt/airflow/jars/delta-spark_2.12-3.3.2.jar:/opt/airflow/jars/delta-storage-3.3.2.jar:/opt/airflow/jars/hadoop-aws-3.2.3.jar:/opt/airflow/jars/mysql-connector-java-8.0.19.jar:/opt/airflow/jars/delta-hive_2.12-3.3.2.jar')\
        .enableHiveSupport()\
        .getOrCreate()



#   .config('spark.jars', '/opt/airflow/jars/aws-java-sdk-bundle-1.12.367.jar,/opt/airflow/jars/delta-core_2.12-2.4.0.jar,/opt/airflow/jars/delta-storage-3.2.0.jar,/opt/airflow/jars/hadoop-aws-3.2.3.jar,/opt/airflow/jars/mysql-connector-java-8.0.19.jar')\
#         .config('spark.driver.extraClassPath', '/opt/airflow/jars/aws-java-sdk-bundle-1.12.367.jar:/opt/airflow/jars/delta-core_2.12-2.4.0.jar:/opt/airflow/jars/delta-storage-3.2.0.jar:/opt/airflow/jars/hadoop-aws-3.2.3.jar:/opt/airflow/jars/mysql-connector-java-8.0.19.jar')\
#         .config('spark.executor.extraClassPath', '/opt/airflow/jars/aws-java-sdk-bundle-1.12.367.jar:/opt/airflow/jars/delta-core_2.12-2.4.0.jar:/opt/airflow/jars/delta-storage-3.2.0.jar:/opt/airflow/jars/hadoop-aws-3.2.3.jar:/opt/airflow/jars/mysql-connector-java-8.0.19.jar')\hy

        # .config('spark.jars', '/opt/airflow/jars/aws-java-sdk-1.12.367.jar,/opt/airflow/jars/delta-core_2.12-2.4.0.jar,/opt/airflow/jars/delta-storage-3.2.0.jar,/opt/airflow/jars/hadoop-aws-3.3.4.jar,/opt/airflow/jars/mysql-connector-java-8.0.19.jar,/opt/airflow/jars/s3-2.18.41.jar,/opt/airflow/jars/aws-java-sdk-core-1.12.367.jar,/opt/airflow/jars/aws-java-sdk-s3-1.12.367.jar')\


        # .config('spark.jars', '/opt/spark/jars/aws-java-sdk-1.12.367.jar,/opt/spark/jars/delta-core_2.12-2.4.0.jar,/opt/spark/jars/delta-storage-3.2.0.jar,/opt/spark/jars/hadoop-aws-3.3.4.jar,/opt/spark/jars/mysql-connector-java-8.0.19.jar,/opt/spark/jars/s3-2.18.41.jar,/opt/spark/jars/aws-java-sdk-core-1.12.367.jar,/opt/spark/jars/aws-java-sdk-s3-1.12.367.jar')\
        #  .config('spark.driver.extraClassPath', '/opt/spark/jars/aws-java-sdk-1.12.367.jar:/opt/spark/jars/delta-core_2.12-2.4.0.jar:/opt/spark/jars/delta-storage-3.2.0.jar:/opt/spark/jars/hadoop-aws-3.3.4.jar:/opt/spark/jars/mysql-connector-java-8.0.19.jar:/opt/spark/jars/s3-2.18.41.jar:/opt/spark/jars/aws-java-sdk-core-1.12.367.jar:/opt/spark/jars/aws-java-sdk-s3-1.12.367.jar')\
        # .config('spark.executor.extraClassPath', '/opt/spark/jars/aws-java-sdk-1.12.367.jar:/opt/spark/jars/delta-core_2.12-2.4.0.jar:/opt/spark/jars/delta-storage-3.2.0.jar:/opt/spark/jars/hadoop-aws-3.3.4.jar:/opt/spark/jars/mysql-connector-java-8.0.19.jar:/opt/spark/jars/s3-2.18.41.jar:/opt/spark/jars/aws-java-sdk-core-1.12.367.jar:/opt/spark/jars/aws-java-sdk-s3-1.12.367.jar')\

        # .config('spark.driver.extraClassPath', '/opt/spark/jars/aws-java-sdk-1.12.367.jar:/opt/spark/jars/delta-core_2.12-2.4.0.jar:/opt/spark/jars/delta-storage-3.2.0.jar:/opt/spark/jars/hadoop-aws-3.3.4.jar:/opt/spark/jars/mysql-connector-java-8.0.19.jar:/opt/spark/jars/s3-2.18.41.jar')\
        # .config('spark.executor.extraClassPath', '/opt/spark/jars/aws-java-sdk-1.12.367.jar:/opt/spark/jars/delta-core_2.12-2.4.0.jar:/opt/spark/jars/delta-storage-3.2.0.jar:/opt/spark/jars/hadoop-aws-3.3.4.jar:/opt/spark/jars/mysql-connector-java-8.0.19.jar:/opt/spark/jars/s3-2.18.41.jar')\

        # .config('spark.jars.packages', 'com.amazonaws:aws-java-sdk:1.12.367,io.delta:delta-core_2.12:2.4.0,io.delta:delta-storage:3.3.2,org.apache.hadoop:hadoop-aws:3.3.4,mysql:mysql-connector-java:8.0.19,software.amazon.awssdk:s3:2.18.41')\

    # .config('spark.jars.packages', 'org.apache.hadoop:hadoop-aws:3.3.4,io.delta:delta-core_2.12:2.4.0')\
    # .config('spark.executor.extraClassPath', '/opt/spark/jars/hadoop-aws-3.3.4.jar:/opt/spark/jars/s3-2.18.41.jar:/opt/spark/jars/aws-java-sdk-1.12.367.jar:/opt/spark/jars/delta-core_2.12-2.4.0.jar:/opt/spark/jars/delta-storage-3.2.0.jar')\


    spark.sparkContext.setLogLevel("INFO")

    return spark
