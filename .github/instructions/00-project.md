---
applyTo: "**/*"
---
# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## プロジェクト概要

このプロジェクトは、株式市場データ分析と機械学習のためのメダリオンアーキテクチャ（Bronze/Silver/Goldレイヤー）を実装するデータレイクハウス基盤です。Apache Airflowによるオーケストレーション、MinIOオブジェクトストレージ、Delta Lakeテーブル形式、Apache Sparkによる分散データ処理を使用しています。

## アーキテクチャ

包括的なデータエンジニアリングスタックを採用：

- **データレイク**: MinIOオブジェクトストレージ + Delta Lakeテーブル形式
- **オーケストレーション**: Apache Airflow（ETL/MLパイプラインスケジューリング）
- **分散処理**: Apache Spark（分散データ処理）
- **MLプラットフォーム**: MLflow（モデル管理）+ Spark MLlib
- **可視化**: Apache Superset、Metabase（ダッシュボード）
- **メタデータ管理**: Hive Metastore（テーブルメタデータ）
- **インフラ**: Docker Composeによるサービスオーケストレーション

### データフローレイヤー

1. **Bronzeレイヤー**: 外部API（Yahoo Finance、ニュース、市場データ）からの生データ取り込み
2. **Silverレイヤー**: データ品質チェック（Deequ使用）によるクリーンアップ済みデータ
3. **Goldレイヤー**: 分析・ML用に特徴量エンジニアリング済みデータ
4. **Feature Store**: 機械学習モデル用の統一特徴量

## 開発コマンド

### 環境セットアップ
```bash
# データプラットフォーム全体を起動
docker-compose up -d

# 特定サービスのみ起動
docker-compose up airflow-scheduler airflow-apiserver airflow-worker

# Airflow UI アクセス
# URL: http://localhost:8080
# ユーザー名: airflow
# パスワード: airflow

# MinIO Console アクセス
# URL: http://localhost:9001
# ユーザー名: minioadmin
# パスワード: minioadmin

# Superset アクセス
# URL: http://localhost:8088

# Metabase アクセス
# URL: http://localhost:3000

# MLflow アクセス
# URL: http://localhost:5000

# Spark Master UI アクセス
# URL: http://localhost:18080
```

### コンテナ管理
```bash
# 全サービス停止
docker-compose down

# Airflowコンテナの変更後リビルド
docker-compose build airflow-scheduler

# ログ確認
docker-compose logs -f airflow-scheduler
docker-compose logs -f airflow-worker
docker-compose logs -f spark-master

# コンテナ内でコマンド実行
docker-compose exec airflow-scheduler bash
docker-compose exec spark-master bash

# 環境リセット（ボリューム削除）
docker-compose down -v
```

### 開発ワークフロー
```bash
# コンテナステータス確認
docker-compose ps

# サービスヘルス監視
docker-compose logs --tail=50 -f [service-name]

# DAG開発・テスト
docker-compose exec airflow-scheduler airflow dags test [dag_id] [execution_date]

# Sparkジョブのデバッグ
docker-compose exec spark-master spark-submit --master spark://spark-master:7077 /path/to/script.py
```

## 主要設定

### Airflow設定
- DAG配置場所: `./airflow/dags/`
- カスタム依存関係: `./airflow/requirements.txt`
- 設定ファイル: `./airflow/config/airflow.cfg`
- 実行エンジン: CeleryExecutor（Redis broker + PostgreSQL backend）
- Sparkオペレーター: SparkSubmitOperatorを使用した分散処理

### データストレージ
- MinIOエンドポイント: `http://minio:9000`（内部）、`http://localhost:9000`（外部）
- Delta Lakeテーブル: MinIOバケット（bronze、silver、gold）に保存
- Hive Metastore: MySQLバックエンドでテーブルメタデータ管理
- S3A統合: `s3a://lakehouse/` パスでアクセス

### Spark設定
- Master: `spark://spark-master:7077`
- Python依存関係: Airflow requirements.txtで管理
- Delta Lake 3.3.2 + S3A FileSystem統合設定済み
- 必要JAR: AWS SDK、Delta Lake、Hadoop AWS、MySQL Connector、Deequ
- スキーマ管理: Hive Metastore統合済み

### 重要なJAR依存関係
```
/opt/spark/jars/ に配置済み:
- aws-java-sdk-bundle-1.12.367.jar
- delta-spark_2.12-3.3.2.jar
- delta-storage-3.3.2.jar
- delta-hive_2.12-3.3.2.jar
- hadoop-aws-3.2.3.jar
- mysql-connector-java-8.0.19.jar
- deequ-2.0.11-spark-3.5.jar
```

## プロジェクト構造

- `airflow/` - Airflow DAG、設定、カスタム依存関係
  - `dags/` - Airflow DAGファイル
  - `scripts/` - Sparkジョブスクリプト
  - `config/` - Airflow設定ファイル
  - `requirements.txt` - Python依存関係
- `doc/` - プロジェクトドキュメント（SPEC.md含む）
- `spark/` - Spark設定とDockerfile
- `hive/` - Hive Metastore設定
- `docker-compose.yml` - 全サービスのオーケストレーション設定

## 実装状況と重要なポイント

### 現在の実装レベル
- **インフラ設定**: 完了（全サービス統合済み）
- **基本DAG**: 実装済み（`ingest_yfinance_to_delta`）
- **データ取り込み**: 部分実装（スキーマ作成メイン）
- **メダリオンアーキテクチャ**: 設計済み、実装は進行中
- **初期データソース**: Apple（AAPL）株価データに焦点

### 技術統合の特徴
- Docker network `shared` によるサービス間通信
- Delta Lakeによるデータ品質保証とACIDトランザクション
- Deequによるデータ品質バリデーション（設定済み）
- MLflowによる実験管理とモデルレジストリ
- 技術指標、センチメント分析、マクロ特徴量のフィーチャーエンジニアリング計画

### Sparkセッション設定パターン
```python
spark = SparkSession.builder.getOrCreate()  # SparkSubmitOperator使用時
```

### データ処理パイプライン
1. **データ取得**: yfinanceライブラリでYahoo Finance APIから株価データ取得
2. **Bronze層保存**: Delta Lake形式でMinIOに生データ保存
3. **Silver層処理**: データクリーニングと品質バリデーション
4. **Gold層変換**: ビジネスロジック適用と特徴量エンジニアリング
5. **ML Pipeline**: MLflowとSpark MLlibによるモデル学習・管理

## トラブルシューティング

### よくある問題
1. **Airflow DAGが表示されない**: `docker-compose logs airflow-scheduler` でパースエラーを確認
2. **Spark接続問題**: spark-masterの健全性とネットワーク接続を確認
3. **MinIOアクセス問題**: サービス間の認証情報とエンドポイント設定を確認
4. **メモリ不足**: スタックには大きなリソースが必要、Dockerメモリ制限を調整
5. **JAR依存関係エラー**: `/opt/spark/jars/` の必要JARファイル存在確認

### サービス依存関係
ヘルスチェックに基づく起動順序。サービス起動失敗時：
1. `docker-compose ps` で失敗サービス確認
2. 失敗サービスのログレビュー
3. 必要ボリュームとネットワーク作成確認
4. システムリソース（メモリ、ディスク容量）確認

### デバッグコマンド
```bash
# Sparkジョブログ確認
docker-compose exec spark-master cat /opt/spark/logs/spark-master-*.out

# Airflow DAGテスト
docker-compose exec airflow-scheduler airflow dags test ingest_yfinance_to_delta 2025-07-27

# MinIOコンソールでデータ確認
# http://localhost:9001 → lakehouse バケット

# Delta Lakeテーブル確認
docker-compose exec spark-master pyspark
# >>> spark.sql("SHOW DATABASES").show()
# >>> spark.sql("SHOW TABLES IN bronze").show()
```

## パフォーマンス最適化

### Spark設定調整
- メモリ設定: `spark.executor.memory`, `spark.driver.memory`
- 並列度: `spark.sql.adaptive.enabled=true`
- Delta Lake最適化: `OPTIMIZE` および `VACUUM` コマンド定期実行

### データ分割戦略
- 日付ベースパーティショニング: `/year/month/day`
- シンボルベースパーティショニング: 複数銘柄対応時

このシステム構成により、エンタープライズグレードのデータレイクハウス基盤が実現され、拡張性と可観測性を持つデータパイプラインが構築されています。
