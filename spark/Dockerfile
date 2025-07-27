FROM apache/spark:3.5.6-scala2.12-java17-python3-ubuntu

USER root

# Install prerequisites
RUN apt-get update && apt-get install -y curl

RUN curl -O https://repo1.maven.org/maven2/com/amazon/deequ/deequ/2.0.11-spark-3.5/deequ-2.0.11-spark-3.5.jar
RUN curl -O https://repo1.maven.org/maven2/com/amazonaws/aws-java-sdk-bundle/1.12.367/aws-java-sdk-bundle-1.12.367.jar
RUN curl -O https://repo1.maven.org/maven2/com/amazonaws/aws-java-sdk/1.12.788/aws-java-sdk-1.12.788.jar
RUN curl -O https://repo1.maven.org/maven2/software/amazon/awssdk/s3/2.31.78/s3-2.31.78.jar
# RUN curl -O https://repo1.maven.org/maven2/io/delta/delta-core_2.12/2.4.0/delta-core_2.12-2.4.0.jar
RUN curl -O https://repo1.maven.org/maven2/io/delta/delta-hive_2.12/3.3.2/delta-hive_2.12-3.3.2.jar
RUN curl -O https://repo1.maven.org/maven2/io/delta/delta-spark_2.12/3.3.2/delta-spark_2.12-3.3.2.jar
RUN curl -O https://repo1.maven.org/maven2/io/delta/delta-storage/3.3.2/delta-storage-3.3.2.jar
RUN curl -O https://repo1.maven.org/maven2/org/apache/hadoop/hadoop-aws/3.3.4/hadoop-aws-3.3.4.jar
RUN curl -O https://repo1.maven.org/maven2/org/apache/hadoop/hadoop-common/3.3.4/hadoop-common-3.3.4.jar
RUN curl -O https://repo1.maven.org/maven2/org/apache/hadoop/hadoop-hdfs/3.3.4/hadoop-hdfs-3.3.4.jar
RUN curl -O https://repo1.maven.org/maven2/mysql/mysql-connector-java/8.0.19/mysql-connector-java-8.0.19.jar
RUN curl -O https://repo1.maven.org/maven2/com/fasterxml/woodstox/woodstox-core/7.1.1/woodstox-core-7.1.1.jar

RUN mkdir -p /opt/spark/jars/
RUN cp deequ-2.0.11-spark-3.5.jar       /opt/spark/jars/
RUN cp aws-java-sdk-bundle-1.12.367.jar /opt/spark/jars/
RUN cp aws-java-sdk-1.12.788.jar        /opt/spark/jars/
RUN cp s3-2.31.78.jar                   /opt/spark/jars/
# RUN cp delta-core_2.12-2.4.0.jar    /opt/spark/jars/
RUN cp delta-hive_2.12-3.3.2.jar        /opt/spark/jars/
RUN cp delta-spark_2.12-3.3.2.jar       /opt/spark/jars/
RUN cp delta-storage-3.3.2.jar          /opt/spark/jars/
RUN cp hadoop-aws-3.3.4.jar             /opt/spark/jars/
RUN cp hadoop-common-3.3.4.jar          /opt/spark/jars/
RUN cp hadoop-hdfs-3.3.4.jar            /opt/spark/jars/
RUN cp mysql-connector-java-8.0.19.jar  /opt/spark/jars/
RUN cp woodstox-core-7.1.1.jar          /opt/spark/jars/
