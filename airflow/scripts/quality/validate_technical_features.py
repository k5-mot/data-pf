#!/usr/bin/env python3
"""
テクニカル指標品質検証スクリプト

Gold層のテクニカル指標データの品質を検証し、異常や問題を検出

Usage:
    spark-submit validate_technical_features.py --input_table gold.technical_features --validation_rules config/technical_validation_rules.yaml
"""

import argparse
import logging
import sys
import json
from typing import Dict, List, Any, Tuple
from datetime import datetime

from pyspark.sql import SparkSession, DataFrame
from pyspark.sql.functions import (
    col, count, sum as spark_sum, avg, min as spark_min, max as spark_max,
    stddev, isnan, isnull, when, lit, current_timestamp, abs as spark_abs,
    percentile_approx, round as spark_round
)

# 既存のspark_session.pyとDelta Lake共通ライブラリを使用
import sys
import os
sys.path.append('/opt/airflow/scripts')
from common.spark_session import get_spark_session
from common.delta_utils import read_from_delta_table, write_to_delta_table

# ログ設定
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)




def get_default_validation_rules() -> Dict[str, Any]:
    """
    デフォルトの検証ルール定義

    Returns:
        Dict: 検証ルール設定
    """
    return {
        "range_checks": {
            "rsi_14d": {"min": 0, "max": 100, "description": "RSI should be between 0 and 100"},
            "volume_ratio": {"min": 0, "max": 50, "description": "Volume ratio should be reasonable"},
            "volatility_20d": {"min": 0, "max": 1.0, "description": "Volatility should be between 0 and 100%"}
        },
        "relationship_checks": {
            "bollinger_bands": {
                "description": "Bollinger upper should be >= middle >= lower",
                "condition": "bollinger_upper >= bollinger_middle AND bollinger_middle >= bollinger_lower"
            },
            "moving_averages": {
                "description": "SMA50 should be smoother than SMA5",
                "check_type": "smoothness"
            },
            "price_coherence": {
                "description": "All moving averages should be close to recent price levels",
                "tolerance": 0.5  # 50% tolerance
            }
        },
        "completeness_checks": {
            "required_fields": [
                "symbol", "feature_date", "sma_20d", "rsi_14d", "macd_line",
                "bollinger_middle", "atr_14d", "volume_sma_20d"
            ],
            "min_completeness_rate": 0.95
        },
        "consistency_checks": {
            "temporal_continuity": {
                "description": "Check for gaps in time series data",
                "max_gap_days": 7
            },
            "value_continuity": {
                "description": "Check for sudden jumps in indicator values",
                "max_change_percentage": 0.3  # 30% max change day-over-day
            }
        },
        "thresholds": {
            "error_rate_threshold": 0.05,  # 5% error rate threshold
            "warning_rate_threshold": 0.10,  # 10% warning rate threshold
            "min_records_per_symbol": 20   # Minimum records per symbol
        }
    }


def validate_range_checks(df: DataFrame, rules: Dict[str, Any]) -> Dict[str, Any]:
    """
    値範囲チェック

    Args:
        df: 検証対象DataFrame
        rules: 範囲チェックルール

    Returns:
        Dict: 検証結果
    """
    logger.info("Performing range checks...")

    results = {}
    total_records = df.count()

    for field, rule in rules.items():
        if field not in df.columns:
            continue

        min_val = rule.get("min")
        max_val = rule.get("max")
        description = rule.get("description", f"Range check for {field}")

        # 範囲外の値をカウント
        out_of_range_condition = (
            (min_val is not None and col(field) < min_val) |
            (max_val is not None and col(field) > max_val)
        )

        out_of_range_count = df.filter(out_of_range_condition & col(field).isNotNull()).count()

        # 統計情報取得
        field_stats = df.select(
            spark_min(field).alias("min"),
            spark_max(field).alias("max"),
            avg(field).alias("avg"),
            count(field).alias("count")
        ).collect()[0]

        error_rate = out_of_range_count / total_records if total_records > 0 else 0

        results[field] = {
            "description": description,
            "total_records": total_records,
            "valid_records": field_stats["count"],
            "out_of_range_count": out_of_range_count,
            "error_rate": error_rate,
            "actual_min": field_stats["min"],
            "actual_max": field_stats["max"],
            "actual_avg": field_stats["avg"],
            "expected_min": min_val,
            "expected_max": max_val,
            "status": "PASS" if error_rate <= 0.05 else "FAIL"
        }

        logger.info(f"Range check {field}: {results[field]['status']} (error rate: {error_rate:.3f})")

    return results


def validate_relationship_checks(df: DataFrame, rules: Dict[str, Any]) -> Dict[str, Any]:
    """
    関係性チェック

    Args:
        df: 検証対象DataFrame
        rules: 関係性チェックルール

    Returns:
        Dict: 検証結果
    """
    logger.info("Performing relationship checks...")

    results = {}
    total_records = df.count()

    # ボリンジャーバンド関係性チェック
    if "bollinger_bands" in rules:
        bollinger_rule = rules["bollinger_bands"]

        # 上部 >= 中央 >= 下部の関係をチェック
        bollinger_violation = df.filter(
            (col("bollinger_upper") < col("bollinger_middle")) |
            (col("bollinger_middle") < col("bollinger_lower")) |
            col("bollinger_upper").isNull() |
            col("bollinger_middle").isNull() |
            col("bollinger_lower").isNull()
        ).count()

        error_rate = bollinger_violation / total_records if total_records > 0 else 0

        results["bollinger_bands"] = {
            "description": bollinger_rule["description"],
            "total_records": total_records,
            "violation_count": bollinger_violation,
            "error_rate": error_rate,
            "status": "PASS" if error_rate <= 0.01 else "FAIL"
        }

    # 移動平均の妥当性チェック
    if "price_coherence" in rules:
        coherence_rule = rules["price_coherence"]
        tolerance = coherence_rule.get("tolerance", 0.5)

        # 移動平均が現在価格から大きく乖離していないかチェック
        # (この例では close_price がないので、移動平均同士の妥当性をチェック)
        coherence_violation = df.filter(
            (spark_abs(col("sma_5d") - col("sma_20d")) / col("sma_20d") > tolerance) |
            (spark_abs(col("sma_20d") - col("sma_50d")) / col("sma_50d") > tolerance)
        ).count()

        error_rate = coherence_violation / total_records if total_records > 0 else 0

        results["price_coherence"] = {
            "description": coherence_rule["description"],
            "total_records": total_records,
            "violation_count": coherence_violation,
            "error_rate": error_rate,
            "tolerance": tolerance,
            "status": "PASS" if error_rate <= 0.05 else "FAIL"
        }

    return results


def validate_completeness_checks(df: DataFrame, rules: Dict[str, Any]) -> Dict[str, Any]:
    """
    完整性チェック

    Args:
        df: 検証対象DataFrame
        rules: 完整性チェックルール

    Returns:
        Dict: 検証結果
    """
    logger.info("Performing completeness checks...")

    results = {}
    total_records = df.count()

    required_fields = rules.get("required_fields", [])
    min_completeness_rate = rules.get("min_completeness_rate", 0.95)

    for field in required_fields:
        if field not in df.columns:
            results[field] = {
                "description": f"Required field {field} missing",
                "status": "FAIL",
                "error": "Field not found"
            }
            continue

        null_count = df.filter(col(field).isNull()).count()
        completeness_rate = (total_records - null_count) / total_records if total_records > 0 else 0

        results[field] = {
            "description": f"Completeness check for {field}",
            "total_records": total_records,
            "null_count": null_count,
            "completeness_rate": completeness_rate,
            "min_required_rate": min_completeness_rate,
            "status": "PASS" if completeness_rate >= min_completeness_rate else "FAIL"
        }

        logger.info(f"Completeness {field}: {results[field]['status']} (rate: {completeness_rate:.3f})")

    return results


def validate_consistency_checks(df: DataFrame, rules: Dict[str, Any]) -> Dict[str, Any]:
    """
    一貫性チェック

    Args:
        df: 検証対象DataFrame
        rules: 一貫性チェックルール

    Returns:
        Dict: 検証結果
    """
    logger.info("Performing consistency checks...")

    results = {}

    # 時系列連続性チェック
    if "temporal_continuity" in rules:
        temporal_rule = rules["temporal_continuity"]
        max_gap_days = temporal_rule.get("max_gap_days", 7)

        # 各銘柄の日付ギャップをチェック
        gap_check_sql = f"""
            SELECT symbol,
                   COUNT(*) as gap_violations
            FROM (
                SELECT symbol, feature_date,
                       LAG(feature_date) OVER (PARTITION BY symbol ORDER BY feature_date) as prev_date,
                       DATEDIFF(feature_date, LAG(feature_date) OVER (PARTITION BY symbol ORDER BY feature_date)) as gap_days
                FROM {df.sql_ctx.table_name if hasattr(df, 'sql_ctx') else 'temp_table'}
            ) gap_analysis
            WHERE gap_days > {max_gap_days}
            GROUP BY symbol
        """

        # 一時テーブル作成してSQL実行
        df.createOrReplaceTempView("temp_table")
        gap_violations = df.sql_ctx.sql(gap_check_sql).collect() if hasattr(df, 'sql_ctx') else []

        total_violations = sum([row["gap_violations"] for row in gap_violations])

        results["temporal_continuity"] = {
            "description": temporal_rule["description"],
            "max_gap_days": max_gap_days,
            "gap_violations": total_violations,
            "symbols_with_gaps": len(gap_violations),
            "status": "PASS" if total_violations == 0 else "WARNING"
        }

    # 値の連続性チェック（急激な変化の検出）
    if "value_continuity" in rules:
        continuity_rule = rules["value_continuity"]
        max_change_pct = continuity_rule.get("max_change_percentage", 0.3)

        # RSIの急激な変化をチェック（例）
        from pyspark.sql.window import Window
        window_spec = Window.partitionBy("symbol").orderBy("feature_date")

        rsi_change_df = df.withColumn("prev_rsi",
                                     col("rsi_14d").lag(1).over(window_spec)) \
                         .withColumn("rsi_change_pct",
                                   spark_abs(col("rsi_14d") - col("prev_rsi")) / col("prev_rsi"))

        sudden_changes = rsi_change_df.filter(
            col("rsi_change_pct") > max_change_pct
        ).count()

        results["value_continuity"] = {
            "description": continuity_rule["description"],
            "max_change_percentage": max_change_pct,
            "sudden_changes_count": sudden_changes,
            "status": "PASS" if sudden_changes < df.count() * 0.01 else "WARNING"
        }

    return results


def calculate_overall_quality_score(validation_results: Dict[str, Dict]) -> Dict[str, Any]:
    """
    総合品質スコア計算

    Args:
        validation_results: 各検証カテゴリの結果

    Returns:
        Dict: 総合品質評価
    """
    logger.info("Calculating overall quality score...")

    # 各カテゴリの重み
    category_weights = {
        "range_checks": 0.3,
        "relationship_checks": 0.3,
        "completeness_checks": 0.25,
        "consistency_checks": 0.15
    }

    category_scores = {}
    total_score = 0.0

    for category, results in validation_results.items():
        if category not in category_weights:
            continue

        # カテゴリ内のテスト成功率計算
        total_tests = len(results)
        passed_tests = sum(1 for result in results.values()
                          if result.get("status") == "PASS")

        category_score = passed_tests / total_tests if total_tests > 0 else 1.0
        category_scores[category] = category_score

        # 重み付き合計に追加
        total_score += category_score * category_weights[category]

    # 品質レベル判定
    if total_score >= 0.95:
        quality_level = "EXCELLENT"
    elif total_score >= 0.85:
        quality_level = "GOOD"
    elif total_score >= 0.70:
        quality_level = "ACCEPTABLE"
    else:
        quality_level = "POOR"

    return {
        "total_score": total_score,
        "quality_level": quality_level,
        "category_scores": category_scores,
        "category_weights": category_weights,
        "timestamp": datetime.now().isoformat()
    }


def generate_validation_report(df: DataFrame, validation_results: Dict, quality_score: Dict) -> str:
    """
    検証レポート生成

    Args:
        df: 元データ
        validation_results: 検証結果
        quality_score: 品質スコア

    Returns:
        str: レポート文字列
    """
    report_lines = []
    report_lines.append("=" * 80)
    report_lines.append("TECHNICAL FEATURES VALIDATION REPORT")
    report_lines.append("=" * 80)
    report_lines.append(f"Timestamp: {quality_score['timestamp']}")
    report_lines.append(f"Total Records: {df.count()}")
    report_lines.append(f"Overall Quality Score: {quality_score['total_score']:.3f}")
    report_lines.append(f"Quality Level: {quality_score['quality_level']}")
    report_lines.append("")

    # カテゴリ別結果
    for category, results in validation_results.items():
        report_lines.append(f"--- {category.upper().replace('_', ' ')} ---")
        for test_name, result in results.items():
            status = result.get("status", "UNKNOWN")
            description = result.get("description", "No description")
            report_lines.append(f"  {test_name}: {status}")
            report_lines.append(f"    {description}")

            # 詳細情報表示
            if "error_rate" in result:
                report_lines.append(f"    Error Rate: {result['error_rate']:.3f}")
            if "completeness_rate" in result:
                report_lines.append(f"    Completeness: {result['completeness_rate']:.3f}")

        report_lines.append("")

    # 推奨アクション
    report_lines.append("--- RECOMMENDATIONS ---")
    if quality_score['total_score'] < 0.70:
        report_lines.append("  ⚠️  URGENT: Data quality issues detected. Review and fix data pipeline.")
    elif quality_score['total_score'] < 0.85:
        report_lines.append("  ⚠️  WARNING: Some data quality issues found. Monitor closely.")
    else:
        report_lines.append("  ✅ Data quality is acceptable. Continue monitoring.")

    report_lines.append("=" * 80)

    return "\n".join(report_lines)


def save_validation_results(spark: SparkSession, results: Dict, table_name: str = "quality.technical_features_validation"):
    """
    検証結果をテーブルに保存

    Args:
        spark: SparkSession
        results: 検証結果
        table_name: 保存先テーブル名
    """
    try:
        # quality スキーマ作成
        spark.sql("CREATE SCHEMA IF NOT EXISTS quality")

        # 結果をDataFrameに変換
        validation_records = []
        timestamp = datetime.now()

        for category, tests in results.items():
            if category == "overall_quality":
                continue

            for test_name, test_result in tests.items():
                record = {
                    "validation_timestamp": timestamp,
                    "category": category,
                    "test_name": test_name,
                    "status": test_result.get("status", "UNKNOWN"),
                    "description": test_result.get("description", ""),
                    "error_rate": test_result.get("error_rate", None),
                    "total_records": test_result.get("total_records", None),
                    "details": json.dumps(test_result)
                }
                validation_records.append(record)

        if validation_records:
            results_df = spark.createDataFrame(validation_records)

            # Delta Lake共通ライブラリを使用
            table_path = "s3a://lakehouse/quality/technical_features_validation/"

            write_to_delta_table(
                df=results_df,
                table_name=table_name,
                table_path=table_path,
                mode="append",
                spark=spark
            )

            logger.info(f"Validation results saved to {table_name}")

    except Exception as e:
        logger.error(f"Failed to save validation results: {str(e)}")


def main():
    """メイン処理"""
    parser = argparse.ArgumentParser(description='Technical Features Validation')
    parser.add_argument('--input_table', required=True, help='検証対象テーブル名')
    parser.add_argument('--validation_rules', help='検証ルールファイルパス (YAML)')
    parser.add_argument('--output_report', help='レポート出力ファイルパス')

    args = parser.parse_args()

    logger.info(f"Starting technical features validation: {args.input_table}")

    # Sparkセッション開始（既存のセッションまたは新規作成）
    spark = SparkSession.getActiveSession()
    if spark is None:
        spark = get_spark_session(SparkSession)

    try:
        # データ読み込み（Delta Lake共通ライブラリ使用）
        logger.info(f"Reading data from {args.input_table}")
        df = read_from_delta_table(args.input_table, spark)

        if df is None:
            logger.error(f"Failed to read data from {args.input_table}")
            return 1

        if df.count() == 0:
            logger.warning("No data found in table")
            return 1

        # 検証ルール読み込み（デフォルト使用）
        validation_rules = get_default_validation_rules()
        logger.info("Using default validation rules")

        # 各種検証実行
        validation_results = {}

        validation_results["range_checks"] = validate_range_checks(
            df, validation_rules["range_checks"]
        )

        validation_results["relationship_checks"] = validate_relationship_checks(
            df, validation_rules["relationship_checks"]
        )

        validation_results["completeness_checks"] = validate_completeness_checks(
            df, validation_rules["completeness_checks"]
        )

        validation_results["consistency_checks"] = validate_consistency_checks(
            df, validation_rules["consistency_checks"]
        )

        # 総合品質スコア計算
        quality_score = calculate_overall_quality_score(validation_results)
        validation_results["overall_quality"] = quality_score

        # レポート生成
        report = generate_validation_report(df, validation_results, quality_score)
        logger.info(f"Validation completed. Quality score: {quality_score['total_score']:.3f}")

        # レポート出力
        print(report)

        if args.output_report:
            with open(args.output_report, 'w') as f:
                f.write(report)
            logger.info(f"Report saved to {args.output_report}")

        # 検証結果保存
        save_validation_results(spark, validation_results)

        # 品質スコアが閾値を下回る場合はエラーで終了
        if quality_score['total_score'] < validation_rules["thresholds"]["error_rate_threshold"]:
            logger.error("Data quality below acceptable threshold")
            return 1

        return 0

    except Exception as e:
        logger.error(f"Fatal error in validation process: {str(e)}")
        return 1

    finally:
        spark.stop()


if __name__ == "__main__":
    sys.exit(main())
