# データレイクハウス開発計画書

## 1. 概要

本文書は、株式市場データ分析・機械学習基盤のためのデータレイクハウス開発計画を記述します。メダリオンアーキテクチャに基づいて4つのデータソース（yfinance、EDINET、e-Stat、NewsRSS）からデータを取得し、テクニカル指標→マクロ指標→ミクロ指標→センチメント指標の順でAirflow DAGパイプラインを構築します。

## 2. データレイクハウス設計

### 2.1 アーキテクチャ概要

```
データソース → Bronze層 → Silver層 → Gold層 → Feature Store
    ↓            ↓         ↓         ↓          ↓
  生データ取得   データ保存  データ品質  特徴量計算   ML統合
```

### 2.2 データソース仕様

#### 2.2.1 Yahoo Finance (yfinance) - テクニカル指標
- **データ内容**: 株価OHLCV、分割・配当情報
- **取得頻度**: 日次（市場終了後）
- **対象銘柄**: 日本株式（AAPL, 7203.T, 6758.T等）
- **生成指標**: SMA、EMA、RSI、MACD、ボリンジャーバンド、ATR

#### 2.2.2 e-Stat API - マクロ指標  
- **データ内容**: 為替レート、GDP、CPI、金利、失業率
- **取得頻度**: 官庁発表に応じて（月次・四半期・年次）
- **生成指標**: 金利スプレッド、為替ボラティリティ、経済成長率

#### 2.2.3 EDINET API - ミクロ指標
- **データ内容**: 有価証券報告書、決算短信、四半期報告書  
- **取得頻度**: 新規提出時（リアルタイム監視）
- **生成指標**: ROE、ROA、PER、PBR、売上成長率、利益率、負債比率

#### 2.2.4 ニュースRSS - センチメント指標
- **データ内容**: ニュース記事タイトル・本文・メタデータ
- **取得頻度**: 4時間毎
- **生成指標**: 感情スコア、トピック分類、重要度スコア

### 2.3 MinIO データレイク構造

```
s3a://lakehouse/
├── bronze/              # 生データレイヤー
│   ├── yfinance/        # 株価生データ
│   ├── edinet/          # 財務報告書生データ  
│   ├── estat/           # 経済統計生データ
│   └── news/            # ニュース生データ
├── silver/              # クリーンデータレイヤー
│   ├── stock_prices/    # 株価クリーンデータ
│   ├── financial_statements/  # 財務諸表クリーンデータ
│   ├── economic_indicators/   # 経済指標クリーンデータ
│   └── news_processed/  # ニュース前処理データ
├── gold/                # 特徴量レイヤー
│   ├── technical_features/    # テクニカル指標
│   ├── fundamental_features/  # ファンダメンタル指標
│   ├── macro_features/        # マクロ指標
│   └── sentiment_features/    # センチメント指標
└── feature_store/       # ML特徴量ストア
    ├── unified_features/      # 統合特徴量
    └── feature_metadata/      # 特徴量メタデータ
```

### 2.4 パーティション戦略

- **日付パーティション**: `year=YYYY/month=MM/day=DD`
- **シンボルパーティション**: `symbol=SYMBOL` （株価・財務データ）
- **データソースパーティション**: `source=SOURCE` （ニュース・統計データ）

## 3. Airflow DAG設計

### 3.1 パイプライン全体アーキテクチャ

```
06:00 technical_indicators_pipeline
        ↓
06:30 macro_indicators_pipeline  
        ↓
07:00 micro_indicators_pipeline
        ↓ 
xx:xx sentiment_indicators_pipeline (4時間毎)
        ↓
08:00 feature_store_pipeline
```

### 3.2 DAG詳細設計

#### 3.2.1 テクニカル指標パイプライン (最優先)

**DAG**: `technical_indicators_pipeline`
- **スケジュール**: 毎日6:00（平日）
- **処理フロー**: yfinance API → Bronze → Silver → Gold

**タスク構成**:
```python
ingest_yfinance_data → clean_stock_data → calculate_technical_features → validate_technical_features
```

**主要処理**:
- Bronze層: yfinance APIからOHLCVデータ取得・保存
- Silver層: データ品質チェック・外れ値処理・標準化
- Gold層: テクニカル指標計算（SMA、RSI、MACD、ボリンジャーバンド等）

#### 3.2.2 マクロ指標パイプライン (第2優先)

**DAG**: `macro_indicators_pipeline`
- **スケジュール**: 毎日6:30（平日）
- **処理フロー**: e-Stat API → Bronze → Silver → Gold

**タスク構成**:
```python
ingest_estat_data → clean_economic_data → calculate_macro_features → validate_macro_features
```

**主要処理**:
- Bronze層: e-Stat APIから経済統計データ取得・保存
- Silver層: 季節調整値選択・単位統一・欠損値補間
- Gold層: マクロ指標計算（金利スプレッド、為替ボラティリティ、経済成長率等）

#### 3.2.3 ミクロ指標パイプライン (第3優先)

**DAG**: `micro_indicators_pipeline`
- **スケジュール**: 毎日7:00（平日）
- **処理フロー**: EDINET API → Bronze → Silver → Gold

**タスク構成**:
```python
ingest_edinet_data → clean_financial_data → calculate_fundamental_features → validate_fundamental_features
```

**主要処理**:
- Bronze層: EDINET APIから財務報告書データ取得・XBRL解析
- Silver層: 連結/単体統一・会計基準統一・科目名マッピング
- Gold層: ファンダメンタル指標計算（ROE、ROA、成長率、効率性指標等）

#### 3.2.4 センチメント指標パイプライン (第4優先)

**DAG**: `sentiment_indicators_pipeline`
- **スケジュール**: 4時間毎
- **処理フロー**: NewsRSS → Bronze → Silver → Gold

**タスク構成**:
```python
ingest_news_rss → clean_news_data → calculate_sentiment_features → validate_sentiment_features
```

**主要処理**:
- Bronze層: 経済ニュースRSSフィード取得・記事メタデータ抽出
- Silver層: テキスト前処理・固有表現抽出・重複除去
- Gold層: センチメント分析・感情分析・トピック分類

#### 3.2.5 Feature Store統合パイプライン (統合)

**DAG**: `feature_store_pipeline`
- **スケジュール**: 毎日8:00（平日）
- **処理フロー**: Gold層データ統合 → Feature Store

**タスク構成**:
```python
[wait_sensors] → unite_features → engineer_features → generate_labels → validate_feature_store
```

**主要処理**:
- 各パイプライン完了をExternalTaskSensorで監視
- 特徴量統合・正規化・時系列アライメント
- 高次特徴量エンジニアリング（ラグ特徴量、交互作用項等）
- 予測ターゲット生成（将来リターン計算）

### 3.3 依存関係とエラーハンドリング

#### 3.3.1 DAG間依存関係
```
technical_indicators (完了) → macro_indicators (開始)
macro_indicators (完了) → micro_indicators (開始)  
micro_indicators (完了) → sentiment_indicators (影響なし)
[全パイプライン完了] → feature_store (開始)
```

#### 3.3.2 エラーハンドリング戦略
```python
default_args = {
    'retries': 3,
    'retry_delay': timedelta(minutes=5),
    'retry_exponential_backoff': True,
    'email_on_failure': True,
    'sla': timedelta(hours=2)
}
```

- **API制限対応**: レート制限検出・待機・代替データソース切り替え
- **品質問題対応**: 品質スコア閾値チェック・アラート通知・手動介入フラグ
- **部分的失敗**: 継続可能な処理設計・差分更新対応

## 4. 開発計画とタイムライン

### 4.1 フェーズ別実装計画

#### Phase 1: テクニカル指標パイプライン (1-2週間)
- **Week 1**: Bronze/Silver層実装・テスト
  - yfinance API連携実装
  - Delta Lake基盤構築
  - データ品質チェック機能
- **Week 2**: Gold層・品質検証実装
  - テクニカル指標計算ロジック
  - 品質スコア算出・異常検知
  - エラーハンドリング・ログ機能

#### Phase 2: マクロ指標パイプライン (1週間)
- e-Stat API連携実装
- 経済統計データ処理ロジック
- マクロ特徴量計算・品質検証

#### Phase 3: ミクロ指標パイプライン (2週間)
- **Week 1**: EDINET API・XBRL解析
  - EDINET API連携
  - XBRL/PDF文書解析
  - 財務データ抽出・変換
- **Week 2**: ファンダメンタル指標計算
  - 財務比率計算ロジック
  - 成長率・効率性指標
  - バリュエーション指標

#### Phase 4: センチメント指標パイプライン (2週間)
- **Week 1**: RSS取得・テキスト前処理
  - ニュースRSSフィード収集
  - テキストクリーニング・正規化
  - 固有表現抽出・エンティティ認識
- **Week 2**: 自然言語処理・センチメント分析
  - 感情分析モデル構築
  - トピック分類・重要度算出
  - 信頼度スコア・品質管理

#### Phase 5: Feature Store統合 (1週間)
- 特徴量統合・時系列アライメント
- 高次特徴量エンジニアリング
- 予測ターゲット生成・検証

#### Phase 6: 監視・運用整備 (1週間)
- アラート・ダッシュボード構築
- パフォーマンス監視・最適化
- デバッグ環境・運用手順整備

### 4.2 実装優先順位

#### 優先度1 (Critical): テクニカル指標
- 株価データは最も基本的なデータソース
- 後続パイプラインでの参照が多い
- 実装・検証が比較的容易

#### 優先度2 (High): マクロ指標
- 市場全体の影響を把握
- テクニカル指標との組み合わせで効果的
- データ更新頻度が低く安定

#### 優先度3 (Medium): ミクロ指標
- 個別企業の詳細分析
- EDINET API・XBRL解析の複雑性
- 四半期更新で時間的余裕

#### 優先度4 (Low): センチメント指標  
- 補完的な情報源
- 自然言語処理の技術的複雑性
- リアルタイム性が求められる

### 4.3 リスク管理

#### 技術リスク
- **EDINET API制限**: 代替データソース（企業IR資料）準備
- **自然言語処理精度**: 事前学習モデル・ルールベース併用
- **データ品質問題**: 厳格な品質チェック・異常検知

#### スケジュールリスク
- **API仕様変更**: 余裕をもった開発期間設定
- **データ量増加**: スケーラビリティ設計・性能監視
- **依存関係問題**: 各フェーズの独立性確保

## 5. ファイル構造と技術仕様

### 5.1 ディレクトリ構造

```
airflow/
├── dags/                            # Airflow DAGファイル
│   ├── technical_indicators_pipeline.py
│   ├── macro_indicators_pipeline.py
│   ├── micro_indicators_pipeline.py
│   ├── sentiment_indicators_pipeline.py
│   └── feature_store_pipeline.py
├── scripts/                         # Spark処理スクリプト
│   ├── bronze/                      # データ取得層
│   │   ├── ingest_yfinance.py
│   │   ├── ingest_estat_data.py
│   │   ├── ingest_edinet_data.py
│   │   └── ingest_news_rss.py
│   ├── silver/                      # データクリーニング層
│   │   ├── clean_stock_data.py
│   │   ├── clean_economic_data.py
│   │   ├── clean_financial_data.py
│   │   └── clean_news_data.py
│   ├── gold/                        # 特徴量計算層
│   │   ├── calculate_technical_features.py
│   │   ├── calculate_macro_features.py
│   │   ├── calculate_fundamental_features.py
│   │   └── calculate_sentiment_features.py
│   ├── feature_store/               # 特徴量統合層
│   │   ├── unite_features.py
│   │   ├── engineer_features.py
│   │   └── generate_labels.py
│   ├── quality/                     # データ品質管理
│   │   ├── validate_technical_features.py
│   │   ├── validate_macro_features.py
│   │   ├── validate_fundamental_features.py
│   │   ├── validate_sentiment_features.py
│   │   └── validate_feature_store.py
│   └── common/                      # 共通ライブラリ
│       ├── spark_session.py (既存)
│       ├── delta_utils.py
│       ├── data_quality.py
│       ├── feature_engineering.py
│       └── logging_utils.py
└── requirements.txt (更新)
```

### 5.2 追加技術要件

#### Python依存関係更新
```
# requirements.txt 追加項目
yfinance>=0.2.28                    # 株価データ取得
requests>=2.31.0                    # HTTP API
beautifulsoup4>=4.12.0             # HTMLパース
feedparser>=6.0.10                 # RSSパース
nltk>=3.8.1                        # 自然言語処理
textblob>=0.17.1                   # 感情分析
scikit-learn>=1.3.0                # 機械学習
pandas-ta>=0.3.14b                 # テクニカル指標計算
pydeequ>=1.1.0                     # データ品質チェック
lxml>=4.9.3                        # XML解析
xmltodict>=0.13.0                  # XML-JSON変換
japanstat>=0.1.0                   # e-Stat API
transformers>=4.35.0               # 自然言語処理
torch>=2.1.0                       # 深層学習
```

#### 共通ライブラリ機能
- **delta_utils.py**: Delta Lake操作（write/read/merge/optimize）
- **data_quality.py**: Deequ品質チェック・異常検知・品質スコア算出
- **feature_engineering.py**: テクニカル指標・正規化・ラグ特徴量・移動統計
- **logging_utils.py**: 構造化ログ・メトリクス・アラート通知

### 5.3 監視・品質管理

#### 監視メトリクス
```python
monitoring_metrics = {
    'execution_time': 'タスク実行時間',
    'record_count': '処理レコード数',
    'error_count': 'エラー件数', 
    'quality_score': 'データ品質スコア',
    'memory_usage': 'メモリ使用量',
    'cpu_usage': 'CPU使用率'
}
```

#### アラート閾値
```python
alert_thresholds = {
    'execution_time_max': '30分',
    'quality_score_min': 0.8,
    'error_rate_max': 0.05,
    'data_latency_max': '2時間'
}
```

#### 品質チェックポイント
- **Bronze層**: データ完整性・スキーマ準拠性
- **Silver層**: ビジネスルール検証・統計的異常
- **Gold層**: 特徴量分布・相関関係
- **Feature Store**: 特徴量品質・ドリフト検出

## 6. 次のステップ

### 6.1 即座の実装タスク
1. **テクニカル指標パイプライン開発開始**
   - Bronze層yfinance取得スクリプト作成
   - Delta Lakeテーブル作成・設定
   - 基本的なテクニカル指標計算実装

2. **共通ライブラリ整備**
   - spark_session.py拡張
   - delta_utils.py作成
   - data_quality.py基本機能実装

3. **開発環境整備**
   - requirements.txt更新
   - ローカルテスト環境構築
   - CI/CD準備

### 6.2 長期的な発展計画
- **追加データソース**: 代替データ（衛星画像、SNS、クレジットカード取引等）
- **リアルタイム処理**: Kafka/Spark Streamingによるストリーミング処理
- **ML自動化**: AutoMLパイプライン・モデル自動更新
- **可視化強化**: リアルタイムダッシュボード・予測結果可視化

この開発計画により、堅牢で拡張性があり、高品質な株式市場データ分析基盤の構築が実現されます。