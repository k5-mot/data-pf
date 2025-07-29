import argparse
import json
import logging

# 既存のspark_session.pyとDelta Lake共通ライブラリを使用
import os
import sys
from datetime import datetime
from typing import Any, Dict, List, Tuple

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql.functions import abs as spark_abs
from pyspark.sql.functions import (
    avg,
    col,
    count,
    current_timestamp,
    isnan,
    isnull,
    lit,
    percentile_approx,
    stddev,
    when,
)
from pyspark.sql.functions import max as spark_max
from pyspark.sql.functions import min as spark_min
from pyspark.sql.functions import round as spark_round
from pyspark.sql.functions import sum as spark_sum

sys.path.append("/opt/airflow/scripts")
from common.delta_utils import read_from_delta_table, write_to_delta_table
from common.spark_session import get_spark_session

# ログ設定
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def main():
    """メイン処理"""
    parser = argparse.ArgumentParser(description="Technical Features Validation")
    parser.add_argument("--input_table", required=True, help="検証対象テーブル名")
    parser.add_argument("--validation_rules", help="検証ルールファイルパス (YAML)")
    parser.add_argument("--output_report", help="レポート出力ファイルパス")

    args = parser.parse_args()

    logger.info(f"Starting technical features validation: {args.input_table}")


if __name__ == "__main__":
    # sys.exit(main())
    print(
        "Airflow DAGs should not be run directly. Please use Airflow CLI or UI to trigger the DAG."
    )
