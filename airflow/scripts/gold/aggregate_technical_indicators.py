#!/usr/bin/env python3
"""Gold層: テクニカル指標計算スクリプト

Silver層のクリーン株価データから各種テクニカル指標を計算し、Gold層に保存

Usage:
    spark-submit calculate_technical_features.py --input_table silver.stock_prices_clean --output_table gold.technical_features --indicators sma,ema,rsi,macd,bollinger,atr
"""

import argparse
import logging
import math

# 既存のspark_session.pyとDelta Lake共通ライブラリを使用
import os
import sys
from typing import Any, Dict, List

from pyspark.sql import DataFrame, SparkSession, Window
from pyspark.sql.functions import abs as spark_abs
from pyspark.sql.functions import (
    avg,
    col,
    count,
    current_timestamp,
    dense_rank,
    exp,
    first,
    greatest,
    isnan,
    isnull,
    lag,
    last,
    lead,
    least,
    lit,
    ntile,
    rank,
    row_number,
    sqrt,
    stddev,
    when,
)
from pyspark.sql.functions import max as spark_max
from pyspark.sql.functions import min as spark_min
from pyspark.sql.functions import sum as spark_sum
from pyspark.sql.types import (
    DateType,
    DecimalType,
    StringType,
    StructField,
    StructType,
    TimestampType,
)

sys.path.append("/opt/airflow/scripts")
from common.delta_utils import read_from_delta_table, write_to_delta_table

# ログ設定
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def define_technical_features_schema() -> StructType:
    """テクニカル指標スキーマ定義."""
    return StructType(
        [
            StructField("symbol", StringType(), False),
            StructField("feature_date", DateType(), False),
            # 移動平均系
            StructField("sma_5d", DecimalType(10, 2), True),
            StructField("sma_20d", DecimalType(10, 2), True),
            StructField("sma_50d", DecimalType(10, 2), True),
            StructField("ema_12d", DecimalType(10, 2), True),
            StructField("ema_26d", DecimalType(10, 2), True),
            # オシレーター系
            StructField("rsi_14d", DecimalType(6, 2), True),
            StructField("macd_line", DecimalType(10, 4), True),
            StructField("macd_signal", DecimalType(10, 4), True),
            StructField("macd_histogram", DecimalType(10, 4), True),
            # ボラティリティ系
            StructField("bollinger_upper", DecimalType(10, 2), True),
            StructField("bollinger_middle", DecimalType(10, 2), True),
            StructField("bollinger_lower", DecimalType(10, 2), True),
            StructField("atr_14d", DecimalType(10, 4), True),
            # 出来高系
            StructField("volume_sma_20d", DecimalType(15, 0), True),
            StructField("volume_ratio", DecimalType(6, 2), True),
            # 価格パターン
            StructField("price_momentum_5d", DecimalType(6, 4), True),
            StructField("price_momentum_20d", DecimalType(6, 4), True),
            StructField("volatility_20d", DecimalType(6, 4), True),
            StructField("feature_timestamp", TimestampType(), False),
        ]
    )


def calculate_moving_averages(df: DataFrame) -> DataFrame:
    """移動平均系指標計算

    Args:
        df: 株価データ

    Returns:
        DataFrame: 移動平均付きデータ
    """
    logger.info("Calculating moving averages...")

    # 銘柄・日付でソートしたウィンドウ
    window_spec = Window.partitionBy("symbol").orderBy("trade_date")

    # SMA (Simple Moving Average)
    sma_5_window = window_spec.rowsBetween(-4, 0)  # 5日間
    sma_20_window = window_spec.rowsBetween(-19, 0)  # 20日間
    sma_50_window = window_spec.rowsBetween(-49, 0)  # 50日間

    df = (
        df.withColumn("sma_5d", avg("close_price").over(sma_5_window))
        .withColumn("sma_20d", avg("close_price").over(sma_20_window))
        .withColumn("sma_50d", avg("close_price").over(sma_50_window))
    )

    # EMA (Exponential Moving Average) 計算用関数
    # EMA = (当日価格 × 平滑化定数) + (前日EMA × (1 - 平滑化定数))
    # 平滑化定数 = 2 / (期間 + 1)

    # EMA 12日
    alpha_12 = 2.0 / (12 + 1)
    ema_12_window = window_spec.rowsBetween(Window.unboundedPreceding, 0)

    # EMA 26日
    alpha_26 = 2.0 / (26 + 1)
    ema_26_window = window_spec.rowsBetween(Window.unboundedPreceding, 0)

    # 簡易EMA計算（初期値はSMAで代用）
    df = df.withColumn(
        "ema_12d",
        when(
            row_number().over(window_spec) <= 12,
            avg("close_price").over(window_spec.rowsBetween(-11, 0)),
        ).otherwise(
            col("close_price") * alpha_12
            + lag("ema_12d").over(window_spec) * (1 - alpha_12)
        ),
    )

    df = df.withColumn(
        "ema_26d",
        when(
            row_number().over(window_spec) <= 26,
            avg("close_price").over(window_spec.rowsBetween(-25, 0)),
        ).otherwise(
            col("close_price") * alpha_26
            + lag("ema_26d").over(window_spec) * (1 - alpha_26)
        ),
    )

    return df


def calculate_rsi(df: DataFrame, period: int = 14) -> DataFrame:
    """RSI (Relative Strength Index) 計算

    Args:
        df: 株価データ
        period: RSI計算期間

    Returns:
        DataFrame: RSI付きデータ
    """
    logger.info(f"Calculating RSI ({period} days)...")

    window_spec = Window.partitionBy("symbol").orderBy("trade_date")

    # 前日との価格差分
    df = df.withColumn(
        "price_diff", col("close_price") - lag("close_price").over(window_spec)
    )

    # 上昇・下降分離
    df = df.withColumn(
        "gain", when(col("price_diff") > 0, col("price_diff")).otherwise(0)
    ).withColumn("loss", when(col("price_diff") < 0, -col("price_diff")).otherwise(0))

    # 平均上昇・下降計算
    rsi_window = window_spec.rowsBetween(-(period - 1), 0)

    df = df.withColumn("avg_gain", avg("gain").over(rsi_window)).withColumn(
        "avg_loss", avg("loss").over(rsi_window)
    )

    # RSI計算
    df = df.withColumn("rs", col("avg_gain") / col("avg_loss")).withColumn(
        "rsi_14d", 100 - (100 / (1 + col("rs")))
    )

    # 不要な中間カラム削除
    df = df.drop("price_diff", "gain", "loss", "avg_gain", "avg_loss", "rs")

    return df


def calculate_macd(df: DataFrame) -> DataFrame:
    """MACD (Moving Average Convergence Divergence) 計算

    Args:
        df: EMA付き株価データ

    Returns:
        DataFrame: MACD付きデータ
    """
    logger.info("Calculating MACD...")

    window_spec = Window.partitionBy("symbol").orderBy("trade_date")

    # MACDライン = EMA12 - EMA26
    df = df.withColumn("macd_line", col("ema_12d") - col("ema_26d"))

    # シグナルライン = MACDラインの9日EMA
    alpha_9 = 2.0 / (9 + 1)

    df = df.withColumn(
        "macd_signal",
        when(
            row_number().over(window_spec) <= 9,
            avg("macd_line").over(window_spec.rowsBetween(-8, 0)),
        ).otherwise(
            col("macd_line") * alpha_9
            + lag("macd_signal").over(window_spec) * (1 - alpha_9)
        ),
    )

    # MACDヒストグラム = MACDライン - シグナルライン
    df = df.withColumn("macd_histogram", col("macd_line") - col("macd_signal"))

    return df


def calculate_bollinger_bands(
    df: DataFrame, period: int = 20, std_dev: float = 2.0
) -> DataFrame:
    """ボリンジャーバンド計算

    Args:
        df: 株価データ
        period: 移動平均期間
        std_dev: 標準偏差倍率

    Returns:
        DataFrame: ボリンジャーバンド付きデータ
    """
    logger.info(f"Calculating Bollinger Bands ({period} days, {std_dev} std)...")

    window_spec = Window.partitionBy("symbol").orderBy("trade_date")
    bollinger_window = window_spec.rowsBetween(-(period - 1), 0)

    # 中央線（移動平均）
    df = df.withColumn("bollinger_middle", avg("close_price").over(bollinger_window))

    # 標準偏差
    df = df.withColumn("price_stddev", stddev("close_price").over(bollinger_window))

    # 上部・下部バンド
    df = df.withColumn(
        "bollinger_upper", col("bollinger_middle") + (col("price_stddev") * std_dev)
    ).withColumn(
        "bollinger_lower", col("bollinger_middle") - (col("price_stddev") * std_dev)
    )

    # 不要カラム削除
    df = df.drop("price_stddev")

    return df


def calculate_atr(df: DataFrame, period: int = 14) -> DataFrame:
    """ATR (Average True Range) 計算

    Args:
        df: 株価データ
        period: ATR計算期間

    Returns:
        DataFrame: ATR付きデータ
    """
    logger.info(f"Calculating ATR ({period} days)...")

    window_spec = Window.partitionBy("symbol").orderBy("trade_date")

    # True Range計算
    df = df.withColumn("prev_close", lag("close_price").over(window_spec))

    df = (
        df.withColumn("tr1", col("high_price") - col("low_price"))
        .withColumn("tr2", spark_abs(col("high_price") - col("prev_close")))
        .withColumn("tr3", spark_abs(col("low_price") - col("prev_close")))
    )

    df = df.withColumn("true_range", greatest("tr1", "tr2", "tr3"))

    # ATR (True Rangeの移動平均)
    atr_window = window_spec.rowsBetween(-(period - 1), 0)
    df = df.withColumn("atr_14d", avg("true_range").over(atr_window))

    # 不要カラム削除
    df = df.drop("prev_close", "tr1", "tr2", "tr3", "true_range")

    return df


def calculate_volume_indicators(df: DataFrame) -> DataFrame:
    """出来高系指標計算

    Args:
        df: 株価データ

    Returns:
        DataFrame: 出来高指標付きデータ
    """
    logger.info("Calculating volume indicators...")

    window_spec = Window.partitionBy("symbol").orderBy("trade_date")
    volume_window = window_spec.rowsBetween(-19, 0)  # 20日間

    # 出来高移動平均
    df = df.withColumn("volume_sma_20d", avg("volume").over(volume_window))

    # 出来高比率（当日出来高 / 20日平均出来高）
    df = df.withColumn(
        "volume_ratio",
        when(
            col("volume_sma_20d") > 0, col("volume") / col("volume_sma_20d")
        ).otherwise(1.0),
    )

    return df


def calculate_momentum_indicators(df: DataFrame) -> DataFrame:
    """モメンタム・ボラティリティ指標計算

    Args:
        df: 株価データ

    Returns:
        DataFrame: モメンタム指標付きデータ
    """
    logger.info("Calculating momentum and volatility indicators...")

    window_spec = Window.partitionBy("symbol").orderBy("trade_date")

    # 価格モメンタム（リターン）
    df = df.withColumn(
        "price_5d_ago", lag("close_price", 5).over(window_spec)
    ).withColumn("price_20d_ago", lag("close_price", 20).over(window_spec))

    df = df.withColumn(
        "price_momentum_5d",
        when(
            col("price_5d_ago") > 0,
            (col("close_price") - col("price_5d_ago")) / col("price_5d_ago"),
        ).otherwise(None),
    ).withColumn(
        "price_momentum_20d",
        when(
            col("price_20d_ago") > 0,
            (col("close_price") - col("price_20d_ago")) / col("price_20d_ago"),
        ).otherwise(None),
    )

    # 価格ボラティリティ（20日間の日次リターンの標準偏差）
    df = df.withColumn(
        "daily_return",
        when(
            lag("close_price").over(window_spec) > 0,
            (col("close_price") - lag("close_price").over(window_spec))
            / lag("close_price").over(window_spec),
        ).otherwise(None),
    )

    volatility_window = window_spec.rowsBetween(-19, 0)
    df = df.withColumn("volatility_20d", stddev("daily_return").over(volatility_window))

    # 不要カラム削除
    df = df.drop("price_5d_ago", "price_20d_ago", "daily_return")

    return df


def select_technical_features(df: DataFrame) -> DataFrame:
    """テクニカル指標カラムのみ選択し、Gold層スキーマに整形

    Args:
        df: 全カラム付きデータ

    Returns:
        DataFrame: テクニカル指標のみのデータ
    """
    logger.info("Selecting technical features for gold layer...")

    # Gold層用カラム選択
    gold_df = df.select(
        col("symbol"),
        col("trade_date").alias("feature_date"),
        # 移動平均系
        col("sma_5d").cast(DecimalType(10, 2)),
        col("sma_20d").cast(DecimalType(10, 2)),
        col("sma_50d").cast(DecimalType(10, 2)),
        col("ema_12d").cast(DecimalType(10, 2)),
        col("ema_26d").cast(DecimalType(10, 2)),
        # オシレーター系
        col("rsi_14d").cast(DecimalType(6, 2)),
        col("macd_line").cast(DecimalType(10, 4)),
        col("macd_signal").cast(DecimalType(10, 4)),
        col("macd_histogram").cast(DecimalType(10, 4)),
        # ボラティリティ系
        col("bollinger_upper").cast(DecimalType(10, 2)),
        col("bollinger_middle").cast(DecimalType(10, 2)),
        col("bollinger_lower").cast(DecimalType(10, 2)),
        col("atr_14d").cast(DecimalType(10, 4)),
        # 出来高系
        col("volume_sma_20d").cast(DecimalType(15, 0)),
        col("volume_ratio").cast(DecimalType(6, 2)),
        # 価格パターン
        col("price_momentum_5d").cast(DecimalType(6, 4)),
        col("price_momentum_20d").cast(DecimalType(6, 4)),
        col("volatility_20d").cast(DecimalType(6, 4)),
        current_timestamp().alias("feature_timestamp"),
    )

    return gold_df


def save_to_gold_table(spark: SparkSession, df: DataFrame, table_name: str) -> bool:
    """Gold層テーブルに保存

    Args:
        spark: SparkSession
        df: 保存するDataFrame
        table_name: 保存先テーブル名

    Returns:
        bool: 保存成功可否
    """
    try:
        if df.count() == 0:
            logger.warning("DataFrame is empty, skipping save")
            return False

        # パーティションカラム追加
        from pyspark.sql.functions import year

        df_with_partitions = df.withColumn("year", year("feature_date"))

        # Delta Lake共通ライブラリを使用
        table_path = "s3a://lakehouse/gold/technical_features/"

        return write_to_delta_table(
            df=df_with_partitions,
            table_name=table_name,
            table_path=table_path,
            mode="merge",
            partition_cols=["year", "symbol"],
            merge_keys=["symbol", "feature_date"],
            spark=spark,
        )

    except Exception as e:
        logger.error(f"Error saving to gold table: {e!s}")
        return False


def create_gold_schema(spark: SparkSession):
    """Gold スキーマ作成"""
    try:
        spark.sql("CREATE SCHEMA IF NOT EXISTS gold")
        logger.info("Gold schema created/verified")
    except Exception as e:
        logger.error(f"Error creating gold schema: {e!s}")


def main():
    """メイン処理"""
    parser = argparse.ArgumentParser(description="Technical Features Calculation")
    parser.add_argument(
        "--input_table", required=True, help="入力テーブル名 (silver layer)"
    )
    parser.add_argument(
        "--output_table", required=True, help="出力テーブル名 (gold layer)"
    )
    parser.add_argument(
        "--indicators",
        default="sma,ema,rsi,macd,bollinger,atr",
        help="計算する指標 (カンマ区切り)",
    )

    args = parser.parse_args()

    # 指標リスト解析
    indicators = [ind.strip().lower() for ind in args.indicators.split(",")]

    logger.info(
        f"Starting technical features calculation: {args.input_table} -> {args.output_table}"
    )
    logger.info(f"Indicators: {indicators}")

    # Sparkセッション開始（既存のセッションまたは新規作成）
    spark = SparkSession.builder.getOrCreate()

    try:
        # Gold スキーマ作成
        create_gold_schema(spark)
        # Silver スキーマ作成（Delta Lakeパスからテーブル作成時に必要）
        try:
            spark.sql("CREATE SCHEMA IF NOT EXISTS silver")
            spark.sql("USE silver")  # スキーマを明示的に選択
            logger.info(
                "Silver schema created/verified (for Delta Lake table creation)"
            )
        except Exception as e:
            logger.error(f"Error creating silver schema: {e!s}")

        # Silver層データ読み込み（Delta Lake共通ライブラリ使用）
        logger.info(f"Reading data from {args.input_table}")
        if not spark.catalog.tableExists(args.input_table):
            logger.warning(
                f"Table {args.input_table} does not exist, trying to create it from Delta Lake path"
            )
            table_path = "s3a://lakehouse/silver/stock_prices/"
            try:
                silver_df = spark.read.format("delta").load(table_path)
                logger.info(
                    f"Successfully read data from Delta Lake path: {table_path}"
                )
                spark.sql(f"DROP TABLE IF EXISTS {args.input_table}")
                spark.sql(f"""
                    CREATE TABLE {args.input_table}
                    USING DELTA
                    LOCATION '{table_path}'
                """)
                logger.info(
                    f"Created Hive table {args.input_table} pointing to {table_path}"
                )
            except Exception as e:
                logger.error(f"Failed to read from Delta Lake path {table_path}: {e!s}")
                return 1
        else:
            silver_df = read_from_delta_table(args.input_table, spark)

        if silver_df is None:
            logger.error(f"Failed to read data from {args.input_table}")
            return 1

        # データを日付順にソート
        silver_df = silver_df.orderBy("symbol", "trade_date")

        # 各指標を順次計算
        features_df = silver_df

        if "sma" in indicators or "ema" in indicators:
            features_df = calculate_moving_averages(features_df)

        if "rsi" in indicators:
            features_df = calculate_rsi(features_df)

        if "macd" in indicators:
            features_df = calculate_macd(features_df)

        if "bollinger" in indicators:
            features_df = calculate_bollinger_bands(features_df)

        if "atr" in indicators:
            features_df = calculate_atr(features_df)

        # 出来高・モメンタム指標は常に計算
        features_df = calculate_volume_indicators(features_df)
        features_df = calculate_momentum_indicators(features_df)

        # Gold層スキーマに整形
        gold_df = select_technical_features(features_df)

        # 十分なデータがある期間のみ保持（50日移動平均が計算できる期間）
        gold_df = gold_df.filter(col("sma_50d").isNotNull())

        logger.info(f"Technical features calculated for {gold_df.count()} records")

        # Gold層テーブルに保存
        if save_to_gold_table(spark, gold_df, args.output_table):
            # 結果統計表示
            result_stats = spark.sql(f"""
                SELECT
                    symbol,
                    COUNT(*) as record_count,
                    MIN(feature_date) as min_date,
                    MAX(feature_date) as max_date,
                    AVG(rsi_14d) as avg_rsi,
                    AVG(volatility_20d) as avg_volatility
                FROM {args.output_table}
                GROUP BY symbol
                ORDER BY symbol
            """)

            logger.info("Gold table statistics:")
            result_stats.show()

            return 0
        logger.error("Failed to save to gold table")
        return 1

    except Exception as e:
        logger.error(f"Fatal error in technical features calculation: {e!s}")
        return 1

    finally:
        spark.stop()


if __name__ == "__main__":
    sys.exit(main())
