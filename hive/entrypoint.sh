#!/bin/bash

export HIVE_CONF_DIR=/opt/hive/conf
export HADOOP_CONF_DIR=/opt/hive/conf

if [ -z "$HADOOP_CLIENT_OPTS" ]; then
  export HADOOP_CLIENT_OPTS="-Xmx1G"
fi

# Debug configuration loading
echo "=== Hive Configuration Debug ==="
echo "HIVE_CONF_DIR: $HIVE_CONF_DIR"
echo "HADOOP_CONF_DIR: $HADOOP_CONF_DIR"
echo "Configuration files in $HIVE_CONF_DIR:"
ls -la $HIVE_CONF_DIR/

echo "Contents of metastore-site.xml:"
cat $HIVE_CONF_DIR/metastore-site.xml

# Initialize schema first, then start the Hive Metastore service
echo "Initializing Hive Metastore schema..."
/opt/hive/bin/schematool -dbType mysql -initSchema || true

echo "Starting Hive Metastore Server with MySQL backend..."
exec /opt/hive/bin/hive --skiphadoopversion --skiphbasecp --service metastore
