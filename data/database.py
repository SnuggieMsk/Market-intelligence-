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

    c.execute("""
        CREATE TABLE IF NOT EXISTS quant_predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scan_id INTEGER NOT NULL,
            ticker TEXT NOT NULL,
            prediction_timestamp TEXT NOT NULL,
            valuations_json TEXT,
            levels_json TEXT,
            predictions_json TEXT,
            summary_json TEXT,
            FOREIGN KEY (scan_id) REFERENCES scan_results(id)
        )
    """)

    c.execute("CREATE INDEX IF NOT EXISTS idx_scan_ticker ON scan_results(ticker)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_scan_time ON scan_results(scan_timestamp)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_agent_scan ON agent_analyses(scan_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_report_scan ON aggregated_reports(scan_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_quant_ticker ON quant_predictions(ticker)")

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


def save_quant_predictions(scan_id, ticker, quant_data):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO quant_predictions
        (scan_id, ticker, prediction_timestamp, valuations_json, levels_json,
         predictions_json, summary_json)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        scan_id,
        ticker,
        datetime.utcnow().isoformat(),
        json.dumps(quant_data.get("valuations", {})),
        json.dumps(quant_data.get("levels", {})),
        json.dumps(quant_data.get("predictions", {})),
        json.dumps(quant_data.get("summary", {})),
    ))
    conn.commit()
    conn.close()


def get_quant_predictions_for_ticker(ticker):
    conn = get_connection()
    row = conn.execute("""
        SELECT * FROM quant_predictions
        WHERE ticker = ?
        ORDER BY prediction_timestamp DESC
        LIMIT 1
    """, (ticker,)).fetchone()
    conn.close()
    if not row:
        return None
    result = dict(row)
    for key in ["valuations_json", "levels_json", "predictions_json", "summary_json"]:
        if result.get(key):
            try:
                result[key] = json.loads(result[key])
            except (json.JSONDecodeError, TypeError):
                pass
    return result


def get_research_analyses_for_ticker(ticker):
    """Get only research agent analyses (not base 36 agents)."""
    from research.research_agents import RESEARCH_ROLES
    research_roles = list(RESEARCH_ROLES)
    conn = get_connection()
    placeholders = ",".join(["?" for _ in research_roles])
    rows = conn.execute(f"""
        SELECT aa.*, sr.scan_timestamp
        FROM agent_analyses aa
        JOIN scan_results sr ON aa.scan_id = sr.id
        WHERE aa.ticker = ? AND aa.agent_role IN ({placeholders})
        ORDER BY aa.analysis_timestamp DESC
    """, (ticker, *research_roles)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_completeness_for_ticker(ticker):
    """
    Check data completeness for a single ticker.
    Looks across ALL scan_ids for the ticker (agents may be linked to an older scan).
    Returns dict with: has_scan, agent_count, research_count, has_quant, has_report, scan_id, best_scan_id.
    """
    from research.research_agents import RESEARCH_ROLES
    research_roles = list(RESEARCH_ROLES)
    conn = get_connection()

    # Latest scan
    scan = conn.execute(
        "SELECT id FROM scan_results WHERE ticker = ? ORDER BY scan_timestamp DESC LIMIT 1",
        (ticker,)
    ).fetchone()
    latest_scan_id = scan["id"] if scan else None

    # Count agents across ALL scan_ids for this ticker (not just latest)
    placeholders = ",".join(["?" for _ in research_roles])
    base_count = conn.execute(
        f"SELECT COUNT(*) as c FROM agent_analyses WHERE ticker = ? AND agent_role NOT IN ({placeholders})",
        (ticker, *research_roles)
    ).fetchone()["c"]
    research_count = conn.execute(
        f"SELECT COUNT(*) as c FROM agent_analyses WHERE ticker = ? AND agent_role IN ({placeholders})",
        (ticker, *research_roles)
    ).fetchone()["c"]

    # Find the scan_id that has the most agent analyses (the "best" scan)
    best_scan = conn.execute(
        "SELECT scan_id, COUNT(*) as c FROM agent_analyses WHERE ticker = ? GROUP BY scan_id ORDER BY c DESC LIMIT 1",
        (ticker,)
    ).fetchone()
    best_scan_id = best_scan["scan_id"] if best_scan else latest_scan_id

    # Quant
    has_quant = conn.execute(
        "SELECT COUNT(*) as c FROM quant_predictions WHERE ticker = ?", (ticker,)
    ).fetchone()["c"] > 0

    # Report
    has_report = conn.execute(
        "SELECT COUNT(*) as c FROM aggregated_reports WHERE ticker = ?", (ticker,)
    ).fetchone()["c"] > 0

    conn.close()

    return {
        "ticker": ticker,
        "scan_id": latest_scan_id,
        "best_scan_id": best_scan_id,
        "has_scan": latest_scan_id is not None,
        "agent_count": base_count,
        "research_count": research_count,
        "has_quant": has_quant,
        "has_report": has_report,
    }


def get_completeness_all():
    """Check completeness for all tickers that have scan results."""
    conn = get_connection()
    tickers = [r["ticker"] for r in conn.execute(
        "SELECT DISTINCT ticker FROM scan_results ORDER BY ticker"
    ).fetchall()]
    conn.close()
    return {t: get_completeness_for_ticker(t) for t in tickers}


def get_scan_result_by_id(scan_id):
    """Fetch a single scan result by its ID."""
    conn = get_connection()
    row = conn.execute("SELECT * FROM scan_results WHERE id = ?", (scan_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_latest_scan_for_ticker(ticker):
    """Fetch the latest scan result for a ticker."""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM scan_results WHERE ticker = ? ORDER BY scan_timestamp DESC LIMIT 1",
        (ticker,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None
