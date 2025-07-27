FROM apache/airflow:3.0.3-python3.10 AS default

USER root
RUN apt-get update && apt-get upgrade -y
RUN apt-get install -y --no-install-recommends \
  freetds-bin \
  build-essential \
  default-libmysqlclient-dev \
  apt-utils \
  curl \
  rsync \
  locales
RUN apt-get install -y --no-install-recommends \
  freetds-dev \
  libkrb5-dev \
  libsasl2-dev \
  libssl-dev \
  libffi-dev \
  libpq-dev \
  git

RUN apt-get install -y openjdk-17-jdk
RUN apt-get autoremove -yqq --purge \
  && apt-get clean  \
  && rm -rf /var/lib/apt/lists/*
COPY requirements.txt /requirements.txt

# RUN curl -O https://repo1.maven.org/maven2/com/amazon/deequ/deequ/2.0.11-spark-3.5/deequ-2.0.11-spark-3.5.jar
# RUN curl -O https://repo1.maven.org/maven2/com/amazonaws/aws-java-sdk-bundle/1.12.367/aws-java-sdk-bundle-1.12.367.jar
# # RUN curl -O https://repo1.maven.org/maven2/io/delta/delta-core_2.12/2.4.0/delta-core_2.12-2.4.0.jar
# RUN curl -O https://repo1.maven.org/maven2/io/delta/delta-hive_2.12/3.3.2/delta-hive_2.12-3.3.2.jar
# RUN curl -O https://repo1.maven.org/maven2/io/delta/delta-spark_2.12/3.3.2/delta-spark_2.12-3.3.2.jar
# RUN curl -O https://repo1.maven.org/maven2/io/delta/delta-storage/3.3.2/delta-storage-3.3.2.jar
# RUN curl -O https://repo1.maven.org/maven2/org/apache/hadoop/hadoop-aws/3.2.3/hadoop-aws-3.2.3.jar
# RUN curl -O https://repo1.maven.org/maven2/mysql/mysql-connector-java/8.0.19/mysql-connector-java-8.0.19.jar

# RUN mkdir -p /opt/airflow/jars/
# RUN cp deequ-2.0.11-spark-3.5.jar       /opt/airflow/jars/
# RUN cp aws-java-sdk-bundle-1.12.367.jar /opt/airflow/jars/
# # RUN cp delta-core_2.12-2.4.0.jar        /opt/airflow/jars/
# RUN cp delta-hive_2.12-3.3.2.jar        /opt/airflow/jars/
# RUN cp delta-spark_2.12-3.3.2.jar       /opt/airflow/jars/
# RUN cp delta-storage-3.3.2.jar          /opt/airflow/jars/
# RUN cp hadoop-aws-3.2.3.jar             /opt/airflow/jars/
# RUN cp mysql-connector-java-8.0.19.jar  /opt/airflow/jars/

USER airflow
ENV JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
ENV SPARK_MASTER_URL=spark://spark-master:7077
ENV SPARK_DEPLOY_MODE=client
RUN pip install --no-cache-dir -r /requirements.txt

# Fix SparkSubmitHook master URL parsing to include spark:// protocol prefix
# This needs to be done after pip install when the package is available
USER root
RUN sed -i 's/conn_data\["master"\] = f"{conn.host}:{conn.port}"/conn_data["master"] = f"spark:\/\/{conn.host}:{conn.port}" if conn.conn_type == "spark" else f"{conn.host}:{conn.port}"/' /home/airflow/.local/lib/python3.10/site-packages/airflow/providers/apache/spark/hooks/spark_submit.py
USER airflow
