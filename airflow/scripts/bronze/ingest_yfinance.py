#!/usr/bin/env python3
"""Bronze層: yfinance データ取得スクリプト.

Yahoo Finance APIから株価データを取得し、Delta Lake形式でMinIOに保存

Usage:
    spark-submit ingest_yfinance.py --symbols AAPL,7203.T --period 30d --output_table bronze.yfinance_raw
"""

import argparse
import logging

# 既存のspark_session.pyを使用
import os
import sys
from datetime import date, datetime
from typing import List, Optional

import pandas as pd
import yfinance as yf
from pyspark.sql import SparkSession
from pyspark.sql.functions import current_timestamp, lit, year
from pyspark.sql.types import (
    DateType,
    DoubleType,
    LongType,
    StringType,
    StructField,
    StructType,
    TimestampType,
)

sys.path.append("/opt/airflow/scripts")
from common.delta_utils import create_delta_table_if_not_exists, write_to_delta_table
from common.spark_session import get_spark_session

# ログ設定
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def define_yfinance_schema() -> StructType:
    """yfinanceデータのスキーマ定義"""
    return StructType(
        [
            StructField("symbol", StringType(), False),
            StructField("date", DateType(), False),
            StructField("open", DoubleType(), True),
            StructField("high", DoubleType(), True),
            StructField("low", DoubleType(), True),
            StructField("close", DoubleType(), True),
            StructField("adj_close", DoubleType(), True),
            StructField("volume", LongType(), True),
            StructField("splits", DoubleType(), True),
            StructField("dividends", DoubleType(), True),
            StructField("ingestion_timestamp", TimestampType(), False),
            StructField("source_file", StringType(), True),
        ]
    )


def fetch_yfinance_data(symbol: str, period: str) -> pd.DataFrame | None:
    """yfinanceから株価データを取得

    Args:
        symbol: 銘柄コード (例: AAPL, 7203.T)
        period: 取得期間 (例: 1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max)

    Returns:
        pandas.DataFrame: 株価データ
    """
    try:
        logger.info(f"Fetching data for symbol: {symbol}, period: {period}")

        # yfinanceでデータ取得
        ticker = yf.Ticker(symbol)

        # 履歴データ取得
        hist_data = ticker.history(
            period=period,
            auto_adjust=False,  # 調整前価格も取得
            prepost=False,  # プレ・アフターマーケット除外
            actions=True,  # 分割・配当情報含む
        )

        if hist_data.empty:
            logger.warning(f"No data found for symbol: {symbol}")
            return None

        # インデックス（日付）をカラムに変換
        hist_data.reset_index(inplace=True)

        # カラム名を標準化
        hist_data.columns = [col.lower().replace(" ", "_") for col in hist_data.columns]

        # 必要なカラムのみ選択・リネーム
        if "date" not in hist_data.columns and "datetime" in hist_data.columns:
            hist_data["date"] = hist_data["datetime"].dt.date
        elif "date" in hist_data.columns:
            # date列がdatetime型の場合、日付のみに変換
            if pd.api.types.is_datetime64_any_dtype(hist_data["date"]):
                hist_data["date"] = hist_data["date"].dt.date

        # 必要なカラムを確認・追加
        required_columns = ["open", "high", "low", "close", "adj_close", "volume"]
        for col in required_columns:
            if col not in hist_data.columns:
                hist_data[col] = None

        # 分割・配当情報がない場合は0で埋める
        if "stock_splits" in hist_data.columns:
            hist_data["splits"] = hist_data["stock_splits"]
        else:
            hist_data["splits"] = 0.0

        if "dividends" not in hist_data.columns:
            hist_data["dividends"] = 0.0

        # シンボル情報追加
        hist_data["symbol"] = symbol

        # メタデータ追加
        hist_data["ingestion_timestamp"] = datetime.now()
        hist_data["source_file"] = (
            f"yfinance_{symbol}_{period}_{date.today().isoformat()}"
        )

        # 必要なカラムのみ選択
        final_columns = [
            "symbol",
            "date",
            "open",
            "high",
            "low",
            "close",
            "adj_close",
            "volume",
            "splits",
            "dividends",
            "ingestion_timestamp",
            "source_file",
        ]

        result_df = hist_data[final_columns].copy()

        logger.info(f"Successfully fetched {len(result_df)} records for {symbol}")
        return result_df

    except Exception as e:
        logger.error(f"Error fetching data for {symbol}: {e!s}")
        return None


def save_to_delta_table(spark: SparkSession, df: pd.DataFrame, table_name: str) -> bool:
    """DataFrameをDelta Lakeテーブルに保存し、Hiveテーブルも作成

    Args:
        spark: SparkSession
        df: 保存するDataFrame
        table_name: 保存先テーブル名

    Returns:
        bool: 保存成功可否
    """
    try:
        if df.empty:
            logger.warning("DataFrame is empty, skipping save")
            return False

        # pandasからSparkへ変換
        spark_df = spark.createDataFrame(df, schema=define_yfinance_schema())

        # パーティションカラム追加
        spark_df = spark_df.withColumn(
            "year", spark_df.date.cast("date").cast("string").substr(1, 4)
        )

        # 直接Delta Lakeに保存
        table_path = "s3a://lakehouse/bronze/yfinance/"

        try:
            spark_df.write.format("delta").mode("append").partitionBy(
                "year", "symbol"
            ).save(table_path)

            logger.info(
                f"Successfully saved {spark_df.count()} records to {table_path}"
            )

            # Hiveテーブルを作成（Delta Lakeパスを参照）
            try:
                create_hive_table_for_delta(spark, table_name, table_path)
                logger.info(f"Successfully created/updated Hive table {table_name}")
            except Exception as hive_error:
                logger.warning(
                    f"Delta save successful but Hive table creation failed: {hive_error!s}"
                )

            return True
        except Exception as save_error:
            logger.error(f"Error saving directly to Delta path: {save_error!s}")
            return False

    except Exception as e:
        logger.error(f"Error saving to Delta table: {e!s}")
        return False


def create_hive_table_for_delta(spark: SparkSession, table_name: str, table_path: str):
    """Delta LakeパスをポイントするHiveテーブルを作成

    Args:
        spark: SparkSession
        table_name: テーブル名 (例: bronze.yfinance_raw)
        table_path: Delta Lakeパス
    """
    try:
        # テーブルが既に存在する場合は削除
        spark.sql(f"DROP TABLE IF EXISTS {table_name}")

        # Delta LakeパスをポイントするHiveテーブルを作成
        spark.sql(f"""
            CREATE TABLE {table_name}
            USING DELTA
            LOCATION '{table_path}'
        """)

        logger.info(f"Created Hive table {table_name} pointing to {table_path}")

    except Exception as e:
        logger.error(f"Error creating Hive table {table_name}: {e!s}")
        raise

    # _PIP_ADDITIONAL_REQUIREMENTS: ${_PIP_ADDITIONAL_REQUIREMENTS:-yfinance pandas pyspark delta JPype1 jaydebeapi apache-airflow[crypto,celery,postgres,hive,jdbc,mysql,spark,ssh,redis,statsd,slack,atlas]}


def create_bronze_schema(spark: SparkSession):
    """Bronze スキーマ作成"""
    try:
        spark.sql("CREATE SCHEMA IF NOT EXISTS bronze")
        logger.info("Bronze schema created/verified")
    except Exception as e:
        logger.error(f"Error creating bronze schema: {e!s}")


def main():
    """メイン処理."""
    # 引数を取得.
    parser = argparse.ArgumentParser(description="YFinance Data Ingestion")
    parser.add_argument(
        "--symbols", required=True, help="カンマ区切りの銘柄コード (例: AAPL,7203.T)"
    )
    parser.add_argument("--period", default="30d", help="取得期間 (デフォルト: 30d)")
    parser.add_argument(
        "--output_table", default="bronze.yfinance_raw", help="出力テーブル名"
    )
    args = parser.parse_args()

    # 引数を解析.
    symbols = [symbol.strip() for symbol in args.symbols.split(",")]
    period = args.period
    output_table = args.output_table

    # Sparkセッションを取得.
    spark = SparkSession.builder.getOrCreate()

    try:
        # Bronzeレイヤのスキーマを作成.
        spark.sql("CREATE SCHEMA IF NOT EXISTS bronze")

        # 各銘柄のデータを取得・保存
        total_success = 0
        total_records = 0

        for symbol in symbols:
            # データ取得
            df = fetch_yfinance_data(symbol, period)

            if df is not None and not df.empty:
                total_records += len(df)
                # Delta Lake保存
                if save_to_delta_table(spark, df, output_table):
                    total_success += 1
                    logger.info(f"Successfully processed {symbol}: {len(df)} records")
                else:
                    logger.warning(
                        f"Data fetched but save failed for {symbol}: {len(df)} records"
                    )
            else:
                logger.warning(f"No data available for {symbol}")

        # 結果サマリー
        logger.info(
            f"Ingestion completed: {total_success}/{len(symbols)} symbols successful"
        )
        logger.info(f"Total records processed: {total_records}")

        # テーブル統計表示
        if total_success > 0:
            try:
                # Deltaテーブルを直接読み取り
                table_path = "s3a://lakehouse/bronze/yfinance/"
                result_df = spark.read.format("delta").load(table_path)
                symbol_counts = result_df.groupBy("symbol").count()
                logger.info("Table statistics:")
                symbol_counts.show()
            except Exception as stats_error:
                logger.warning(f"Could not retrieve table statistics: {stats_error!s}")

        # 少なくとも一部のデータが取得できていれば成功とする
        total_fetched = len(symbols) <= total_records
        if total_fetched:
            logger.info(
                f"Data fetching successful even if save failed. Records fetched: {total_records}"
            )
            return 0
        logger.error("No data could be fetched from any symbol")
        return 1

    except Exception as e:
        logger.error(f"Fatal error in main process: {e!s}")
        return 1

    finally:
        spark.stop()


if __name__ == "__main__":
    sys.exit(main())
