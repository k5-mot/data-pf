FROM apache/hive:3.1.3

USER root

# Install curl for downloading JAR files
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# # Download required JAR files for S3A and Delta Lake support
# RUN curl -O https://repo1.maven.org/maven2/com/amazon/deequ/deequ/2.0.11-spark-3.5/deequ-2.0.11-spark-3.5.jar
# RUN curl -O https://repo1.maven.org/maven2/com/amazonaws/aws-java-sdk-bundle/1.12.367/aws-java-sdk-bundle-1.12.367.jar
# # RUN curl -O https://repo1.maven.org/maven2/io/delta/delta-core_2.12/2.4.0/delta-core_2.12-2.4.0.jar
# RUN curl -O https://repo1.maven.org/maven2/io/delta/delta-hive_2.12/3.3.2/delta-hive_2.12-3.3.2.jar
# RUN curl -O https://repo1.maven.org/maven2/io/delta/delta-spark_2.12/3.3.2/delta-spark_2.12-3.3.2.jar
# RUN curl -O https://repo1.maven.org/maven2/io/delta/delta-storage/3.2.0/delta-storage-3.2.0.jar
# RUN curl -O https://repo1.maven.org/maven2/org/apache/hadoop/hadoop-aws/3.2.3/hadoop-aws-3.2.3.jar
# RUN curl -O https://repo1.maven.org/maven2/mysql/mysql-connector-java/8.0.19/mysql-connector-java-8.0.19.jar

# RUN mkdir -p /opt/hive/lib/
# RUN cp deequ-2.0.11-spark-3.5.jar       /opt/hive/lib/
# RUN cp aws-java-sdk-bundle-1.12.367.jar /opt/hive/lib/
# # RUN cp delta-core_2.12-2.4.0.jar        /opt/hive/lib/
# RUN cp delta-hive_2.12-3.3.2.jar        /opt/hive/lib/
# RUN cp delta-spark_2.12-3.3.2.jar       /opt/hive/lib/
# RUN cp delta-storage-3.2.0.jar          /opt/hive/lib/
# RUN cp hadoop-aws-3.2.3.jar             /opt/hive/lib/
# RUN cp mysql-connector-java-8.0.19.jar  /opt/hive/lib/

# Copy custom configuration files
COPY entrypoint.sh /entrypoint.sh
COPY metastore-site.xml /opt/hive/conf/metastore-site.xml

# Set proper permissions
RUN chown -R hive:hive /opt/hive/lib/ && \
  chown -R hive:hive /opt/hive/conf/ && \
  chown hive:hive /entrypoint.sh && chmod +x /entrypoint.sh

USER hive
ENTRYPOINT ["/entrypoint.sh"]
