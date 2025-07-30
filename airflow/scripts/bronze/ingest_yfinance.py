#!/usr/bin/env python3
"""Bronze層: yfinance データ取得スクリプト.

Yahoo Finance APIから株価データを取得し、Delta Lake形式でMinIOに保存

Usage:
    spark-submit ingest_yfinance.py --symbols AAPL,7203.T --period 30d --output_table bronze.yfinance_raw
"""

import argparse
import logging
import sys
from datetime import date, datetime

import pandas as pd
import yfinance as yf
from pyspark.sql import SparkSession
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
sys.path.append("..")
# from common.delta_utils import create_delta_table_if_not_exists, write_to_delta_table

# ログ設定
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def define_yfinance_schema() -> StructType:
    """yfinanceデータのスキーマ定義."""
    return StructType(
        [
            StructField("symbol", StringType(), nullable=False),
            StructField("date", DateType(), nullable=False),
            StructField("open", DoubleType(), nullable=True),
            StructField("high", DoubleType(), nullable=True),
            StructField("low", DoubleType(), nullable=True),
            StructField("close", DoubleType(), nullable=True),
            StructField("adj_close", DoubleType(), nullable=True),
            StructField("volume", LongType(), nullable=True),
            StructField("splits", DoubleType(), nullable=True),
            StructField("dividends", DoubleType(), nullable=True),
            StructField("ingestion_timestamp", TimestampType(), nullable=False),
            StructField("source_file", StringType(), nullable=True),
        ]
    )


def fetch_from_yfinance(symbol: str, period: str) -> pd.DataFrame | None:
    """yfinanceから株価データを取得.

    Args:
        symbol: 銘柄コード (例: AAPL, 7203.T)
        period: 取得期間 (例: 1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max)

    Returns:
        pandas.DataFrame: 株価データ
    """
    try:
        # 銘柄を指定.
        ticker = yf.Ticker(symbol)

        # 過去の株価データを取得.
        df = ticker.history(
            period=period,
            auto_adjust=True,  # 調整後終値は含む.
            prepost=False,  # 時間外取引は除く.
            actions=True,  # 分割・配当情報は含む.
        )

        # データフレームが空でないか確認.
        if df is None or df.empty:
            msg = f"No data found for symbol: {symbol}"
            logger.error(msg)
            return None

        # インデックス（日付）をカラムに変換
        df = df.reset_index()

        # カラム名を標準化
        df.columns = [col.lower().replace(" ", "_") for col in df.columns]

        # 必要なカラムのみ選択・リネーム
        if "date" not in df.columns and "datetime" in df.columns:
            df["date"] = df["datetime"].dt.date
        elif "date" in df.columns:
            # date列がdatetime型の場合、日付のみに変換
            if pd.api.types.is_datetime64_any_dtype(df["date"]):
                df["date"] = df["date"].dt.date

        # 必要なカラムを確認・追加
        required_columns = ["open", "high", "low", "close", "adj_close", "volume"]
        for col in required_columns:
            if col not in df.columns:
                df[col] = None

        # 分割・配当情報がない場合は0で埋める
        if "stock_splits" in df.columns:
            df["splits"] = df["stock_splits"]
        else:
            df["splits"] = 0.0

        if "dividends" not in df.columns:
            df["dividends"] = 0.0

        # シンボル情報追加
        df["symbol"] = symbol

        # メタデータ追加
        df["ingestion_timestamp"] = datetime.now()
        df["source_file"] = f"yfinance_{symbol}_{period}_{date.today().isoformat()}"

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

        result_df = df[final_columns].copy()

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


def ingest_yfinance_data(
    symbol: str, period: str, output_table: str, spark: SparkSession
) -> bool:
    """yfinanceデータを取得し、bronze.yfinanceテーブルにsymbol/yearパーティションで保存."""
    try:
        # yfinance APIからデータを取得
        df = fetch_from_yfinance(symbol, period)

        # データフレームが空でないか確認
        if df is None or df.empty:
            logger.warning(f"No data available for {symbol}")
            return False

        # pandas DataFrame を Spark DataFrame に変換
        spark_df = spark.createDataFrame(df, schema=define_yfinance_schema())

        # yearカラムを追加
        spark_df = spark_df.withColumn(
            "year", spark_df.date.cast("date").cast("string").substr(1, 4)
        )

        # Delta Lakeテーブルパス.
        table_path = "s3a://lakehouse/bronze/yfinance/"

        # symbol/yearパーティションでDelta Lakeに保存
        spark_df.write.format("delta").mode("append").partitionBy(
            "symbol", "year"
        ).save(table_path)

        logger.info(
            f"Successfully saved {spark_df.count()} records for {symbol} to {table_path}"
        )

        # bronze.yfinanceテーブルが存在しない場合は作成
        try:
            spark.sql("CREATE SCHEMA IF NOT EXISTS bronze")
            spark.sql(f"""
                CREATE TABLE IF NOT EXISTS {output_table}
                USING DELTA
                LOCATION '{table_path}'
            """)
            logger.info(f"Created/updated table {output_table}")
        except Exception as table_error:
            logger.warning(f"Table creation warning: {table_error}")

        return True

    except Exception as e:
        logger.error(f"Error in data ingestion for {symbol}: {e}")
        return False


def main() -> int:
    """メイン処理."""
    # 引数を取得.
    parser = argparse.ArgumentParser(description="YFinance Data Ingestion")
    parser.add_argument(
        "--symbols", required=True, help="カンマ区切りの銘柄コード (例: AAPL,7203.T)"
    )
    parser.add_argument("--period", default="1d", help="取得期間 (デフォルト: 1d)")
    parser.add_argument(
        "--output_table", default="bronze.yfinance_raw", help="出力テーブル名"
    )
    args = parser.parse_args()

    # 引数を解析.
    symbols = [symbol.strip() for symbol in args.symbols.split(",")]
    period = str(args.period)
    output_table = str(args.output_table)

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
            df = fetch_from_yfinance(symbol, period)
            print(df)

        #     if df is not None and not df.empty:
        #         total_records += len(df)
        #         # Delta Lake保存
        #         if save_to_delta_table(spark, df, output_table):
        #             total_success += 1
        #             logger.info(f"Successfully processed {symbol}: {len(df)} records")
        #         else:
        #             logger.warning(
        #                 f"Data fetched but save failed for {symbol}: {len(df)} records"
        #             )
        #     else:
        #         logger.warning(f"No data available for {symbol}")

        # # 結果サマリー
        # logger.info(
        #     f"Ingestion completed: {total_success}/{len(symbols)} symbols successful"
        # )
        # logger.info(f"Total records processed: {total_records}")

        # # テーブル統計表示
        # if total_success > 0:
        #     try:
        #         # Deltaテーブルを直接読み取り
        #         table_path = "s3a://lakehouse/bronze/yfinance/"
        #         result_df = spark.read.format("delta").load(table_path)
        #         symbol_counts = result_df.groupBy("symbol").count()
        #         logger.info("Table statistics:")
        #         symbol_counts.show()
        #     except Exception as stats_error:
        #         logger.warning(f"Could not retrieve table statistics: {stats_error!s}")

        # # 少なくとも一部のデータが取得できていれば成功とする
        # total_fetched = len(symbols) <= total_records
        # if total_fetched:
        #     logger.info(
        #         f"Data fetching successful even if save failed. Records fetched: {total_records}"
        #     )
        #     return 0
        # logger.error("No data could be fetched from any symbol")
        # return 1

    except Exception as e:
        logger.error(f"Fatal error in main process: {e!s}")
        return 1

    finally:
        spark.stop()


if __name__ == "__main__":
    sys.exit(main())
