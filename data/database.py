"""
SQLite database layer for persisting scan results, agent analyses, and aggregated reports.
"""

import sqlite3
import json
import os
from datetime import datetime
from config.settings import DATABASE_PATH


def get_connection():
    os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = get_connection()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS scan_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            scan_timestamp TEXT NOT NULL,
            composite_score REAL NOT NULL,
            metrics_json TEXT NOT NULL,
            standout_reasons TEXT,
            company_name TEXT,
            sector TEXT,
            market_cap REAL,
            current_price REAL
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS agent_analyses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scan_id INTEGER NOT NULL,
            ticker TEXT NOT NULL,
            agent_name TEXT NOT NULL,
            agent_role TEXT NOT NULL,
            analysis_timestamp TEXT NOT NULL,
            verdict TEXT NOT NULL,
            confidence REAL,
            reasoning TEXT NOT NULL,
            key_points TEXT,
            risks TEXT,
            catalysts TEXT,
            score REAL,
            raw_response TEXT,
            FOREIGN KEY (scan_id) REFERENCES scan_results(id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS aggregated_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scan_id INTEGER NOT NULL,
            ticker TEXT NOT NULL,
            report_timestamp TEXT NOT NULL,
            overall_verdict TEXT NOT NULL,
            overall_score REAL,
            bull_case TEXT,
            bear_case TEXT,
            consensus_summary TEXT,
            data_summary TEXT,
            sentiment_summary TEXT,
            prediction_summary TEXT,
            agent_agreement_pct REAL,
            key_risks TEXT,
            key_catalysts TEXT,
            recommendation TEXT,
            full_report_json TEXT,
            FOREIGN KEY (scan_id) REFERENCES scan_results(id)
        )
    """)

    c.execute("CREATE INDEX IF NOT EXISTS idx_scan_ticker ON scan_results(ticker)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_scan_time ON scan_results(scan_timestamp)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_agent_scan ON agent_analyses(scan_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_report_scan ON aggregated_reports(scan_id)")

    conn.commit()
    conn.close()


def save_scan_result(ticker, composite_score, metrics, standout_reasons,
                     company_name, sector, market_cap, current_price):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO scan_results
        (ticker, scan_timestamp, composite_score, metrics_json, standout_reasons,
         company_name, sector, market_cap, current_price)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        ticker,
        datetime.utcnow().isoformat(),
        composite_score,
        json.dumps(metrics),
        json.dumps(standout_reasons) if isinstance(standout_reasons, list) else standout_reasons,
        company_name,
        sector,
        market_cap,
        current_price,
    ))
    scan_id = c.lastrowid
    conn.commit()
    conn.close()
    return scan_id


def save_agent_analysis(scan_id, ticker, agent_name, agent_role, analysis):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO agent_analyses
        (scan_id, ticker, agent_name, agent_role, analysis_timestamp,
         verdict, confidence, reasoning, key_points, risks, catalysts, score, raw_response)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        scan_id,
        ticker,
        agent_name,
        agent_role,
        datetime.utcnow().isoformat(),
        analysis.get("verdict", "NEUTRAL"),
        analysis.get("confidence", 0.5),
        analysis.get("reasoning", ""),
        json.dumps(analysis.get("key_points", [])),
        json.dumps(analysis.get("risks", [])),
        json.dumps(analysis.get("catalysts", [])),
        analysis.get("score", 5.0),
        json.dumps(analysis),
    ))
    conn.commit()
    conn.close()


def save_aggregated_report(scan_id, ticker, report):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO aggregated_reports
        (scan_id, ticker, report_timestamp, overall_verdict, overall_score,
         bull_case, bear_case, consensus_summary, data_summary, sentiment_summary,
         prediction_summary, agent_agreement_pct, key_risks, key_catalysts,
         recommendation, full_report_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        scan_id,
        ticker,
        datetime.utcnow().isoformat(),
        report.get("overall_verdict", "HOLD"),
        report.get("overall_score", 5.0),
        report.get("bull_case", ""),
        report.get("bear_case", ""),
        report.get("consensus_summary", ""),
        report.get("data_summary", ""),
        report.get("sentiment_summary", ""),
        report.get("prediction_summary", ""),
        report.get("agent_agreement_pct", 0),
        json.dumps(report.get("key_risks", [])),
        json.dumps(report.get("key_catalysts", [])),
        report.get("recommendation", ""),
        json.dumps(report),
    ))
    conn.commit()
    conn.close()


def get_latest_scan_results(limit=20):
    conn = get_connection()
    rows = conn.execute("""
        SELECT * FROM scan_results
        ORDER BY scan_timestamp DESC, composite_score DESC
        LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_agent_analyses_for_scan(scan_id):
    conn = get_connection()
    rows = conn.execute("""
        SELECT * FROM agent_analyses WHERE scan_id = ?
        ORDER BY agent_name
    """, (scan_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_latest_reports(limit=10):
    conn = get_connection()
    rows = conn.execute("""
        SELECT ar.*, sr.company_name, sr.sector, sr.current_price, sr.market_cap
        FROM aggregated_reports ar
        JOIN scan_results sr ON ar.scan_id = sr.id
        ORDER BY ar.report_timestamp DESC
        LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_report_for_ticker(ticker):
    conn = get_connection()
    row = conn.execute("""
        SELECT ar.*, sr.company_name, sr.sector, sr.current_price, sr.market_cap,
               sr.metrics_json, sr.standout_reasons
        FROM aggregated_reports ar
        JOIN scan_results sr ON ar.scan_id = sr.id
        WHERE ar.ticker = ?
        ORDER BY ar.report_timestamp DESC
        LIMIT 1
    """, (ticker,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_analyses_for_ticker(ticker):
    conn = get_connection()
    rows = conn.execute("""
        SELECT aa.*, sr.scan_timestamp
        FROM agent_analyses aa
        JOIN scan_results sr ON aa.scan_id = sr.id
        WHERE aa.ticker = ?
        ORDER BY aa.analysis_timestamp DESC
    """, (ticker,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]
