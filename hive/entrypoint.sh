#!/bin/bash

export HIVE_CONF_DIR=/opt/hive/conf

if [ -z "$HADOOP_CLIENT_OPTS" ]; then
  export HADOOP_CLIENT_OPTS="-Xmx1G"
fi

# Start the Hive Metastore service directly without schema initialization
echo "Starting Hive Metastore Server with MySQL backend..."
exec /opt/hive/bin/hive --skiphadoopversion --skiphbasecp --service metastore
