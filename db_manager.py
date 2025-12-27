# import psycopg2
# from contextlib import contextmanager
# from typing import Dict, Any, List, Optional, Tuple
# from datetime import datetime
# from config import DB_CONFIG

# # =========================
# # DB CONNECTION
# # =========================
# @contextmanager
# def get_conn():
#     conn = psycopg2.connect(**DB_CONFIG)
#     try:
#         yield conn
#     finally:
#         conn.close()

# # =========================
# # REGISTERED VEHICLES
# # =========================
# def insert_registered_plate_event(
#     plate_number: str,
#     event_type: str
# ) -> Optional[Tuple[int, datetime]]:
#     with get_conn() as conn:
#         cur = conn.cursor()
#         cur.execute(
#             "SELECT id FROM vehicle WHERE vehicle_number = %s",
#             (plate_number,)
#         )
#         row = cur.fetchone()
#         if not row:
#             return None

#         vehicle_id = row[0]
#         cur.execute("""
#             INSERT INTO vehicle_tracking (vehicle_id, date_time, type)
#             VALUES (%s, NOW(), %s)
#             RETURNING id, date_time
#         """, (vehicle_id, event_type))

#         result = cur.fetchone()
#         conn.commit()
#         return result

# # =========================
# # UNREGISTERED VEHICLES
# # =========================
# def insert_unregistered_plate_event(
#     session_id: str,
#     plate_number: str,
#     status: str
# ) -> Optional[Tuple[int, datetime]]:
#     with get_conn() as conn:
#         cur = conn.cursor()
#         cur.execute("""
#             INSERT INTO unregistered_plates
#             (session_id, unregistered_plate_number, status, detected_at)
#             VALUES (%s, %s, %s, NOW())
#             RETURNING id, detected_at
#         """, (session_id, plate_number, status))

#         res = cur.fetchone()
#         conn.commit()
#         return res

# def delete_plate_by_session(session_id: str):
#     with get_conn() as conn:
#         cur = conn.cursor()
#         cur.execute(
#             "DELETE FROM unregistered_plates WHERE session_id = %s",
#             (session_id,)
#         )
#         conn.commit()

# def update_plate_by_session(session_id: str, plate_number: str) -> bool:
#     with get_conn() as conn:
#         cur = conn.cursor()
#         cur.execute("""
#             UPDATE unregistered_plates
#             SET unregistered_plate_number = %s
#             WHERE session_id = %s
#         """, (plate_number, session_id))
#         conn.commit()
#         return cur.rowcount > 0

# def is_registered_plate(plate_number: str) -> bool:
#     with get_conn() as conn:
#         cur = conn.cursor()
#         cur.execute(
#             "SELECT 1 FROM vehicle WHERE vehicle_number = %s",
#             (plate_number,)
#         )
#         return cur.fetchone() is not None

# # =========================
# # FETCH EVENTS
# # =========================
# def get_recent_registered_events(limit=100) -> List[Dict[str, Any]]:
#     with get_conn() as conn:
#         cur = conn.cursor()
#         cur.execute("""
#             SELECT v.vehicle_number, vt.date_time, vt.type,
#                    o.name, o.phone, o.address
#             FROM vehicle_tracking vt
#             JOIN vehicle v ON vt.vehicle_id = v.id
#             LEFT JOIN owner o ON v.owner_id = o.id
#             ORDER BY vt.date_time DESC
#             LIMIT %s
#         """, (limit,))
#         rows = cur.fetchall()

#     return [{
#         "vehicle_number": r[0],
#         "date_time": r[1].isoformat(),
#         "type": r[2],
#         "owner_name": r[3],
#         "owner_phone": r[4],
#         "owner_address": r[5],
#     } for r in rows]

# def get_recent_unregistered_events(limit=100) -> List[Dict[str, Any]]:
#     with get_conn() as conn:
#         cur = conn.cursor()
#         cur.execute("""
#             SELECT session_id, unregistered_plate_number,
#                    status, detected_at
#             FROM unregistered_plates
#             ORDER BY detected_at DESC
#             LIMIT %s
#         """, (limit,))
#         rows = cur.fetchall()

#     return [{
#         "session_id": r[0],
#         "plate_number": r[1],
#         "status": r[2],
#         "detected_at": r[3].isoformat()
#     } for r in rows]



# db_manager.py
import psycopg2
from contextlib import contextmanager
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from config import DB_CONFIG

# =========================
# DB CONNECTION
# =========================
@contextmanager
def get_conn():
    conn = psycopg2.connect(**DB_CONFIG)
    try:
        yield conn
    finally:
        conn.close()

# =========================
# REGISTERED VEHICLES
# =========================
def insert_registered_plate_event(
    plate_number: str,
    event_type: str
) -> Optional[Tuple[int, datetime]]:
    with get_conn() as conn:
        cur = conn.cursor()

        cur.execute(
            "SELECT id FROM vehicle WHERE vehicle_number = %s",
            (plate_number,)
        )
        row = cur.fetchone()
        if not row:
            return None

        vehicle_id = row[0]

        cur.execute("""
            INSERT INTO vehicle_tracking (vehicle_id, date_time, type)
            VALUES (%s, NOW(), %s)
            RETURNING id, date_time
        """, (vehicle_id, event_type))

        result = cur.fetchone()
        conn.commit()
        return result

# =========================
# UNREGISTERED VEHICLES
# =========================
def insert_unregistered_plate_event(
    session_id: str,
    plate_number: str,
    status: str
) -> Optional[Tuple[int, datetime]]:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO unregistered_plates
            (session_id, unregistered_plate_number, status, detected_at)
            VALUES (%s, %s, %s, NOW())
            RETURNING id, detected_at
        """, (session_id, plate_number, status))

        res = cur.fetchone()
        conn.commit()
        return res

def delete_plate_by_session(session_id: str):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM unregistered_plates WHERE session_id = %s",
            (session_id,)
        )
        conn.commit()

def update_plate_by_session(session_id: str, plate_number: str) -> bool:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            UPDATE unregistered_plates
            SET unregistered_plate_number = %s
            WHERE session_id = %s
        """, (plate_number, session_id))
        conn.commit()
        return cur.rowcount > 0

def is_registered_plate(plate_number: str) -> bool:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT 1 FROM vehicle WHERE vehicle_number = %s",
            (plate_number,)
        )
        return cur.fetchone() is not None

# =========================
# FETCH EVENTS
# =========================
def get_recent_registered_events(limit=100) -> List[Dict[str, Any]]:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT v.vehicle_number, vt.date_time, vt.type,
                   o.name, o.phone, o.address
            FROM vehicle_tracking vt
            JOIN vehicle v ON vt.vehicle_id = v.id
            LEFT JOIN owner o ON v.owner_id = o.id
            ORDER BY vt.date_time DESC
            LIMIT %s
        """, (limit,))
        rows = cur.fetchall()

    return [{
        "vehicle_number": r[0],
        "date_time": r[1].isoformat(),
        "type": r[2],
        "owner_name": r[3],
        "owner_phone": r[4],
        "owner_address": r[5],
    } for r in rows]

def get_recent_unregistered_events(limit=100) -> List[Dict[str, Any]]:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT session_id, unregistered_plate_number,
                   status, detected_at
            FROM unregistered_plates
            ORDER BY detected_at DESC
            LIMIT %s
        """, (limit,))
        rows = cur.fetchall()

    return [{
        "session_id": r[0],
        "plate_number": r[1],
        "status": r[2],
        "detected_at": r[3].isoformat()
    } for r in rows]

# ============================================================
# 🔥 CRITICAL FIX: RESTORE LAST IN/OUT STATE AFTER RESTART
# ============================================================
def get_last_plate_status():
    """
    Returns:
    {
        'MH12AB1234': ('IN', datetime),
        'KA01CD5678': ('OUT', datetime)
    }
    """
    query = """
        SELECT v.vehicle_number, vt.type, vt.date_time
        FROM vehicle_tracking vt
        JOIN vehicle v ON vt.vehicle_id = v.id
        WHERE (v.id, vt.date_time) IN (
            SELECT vehicle_id, MAX(date_time)
            FROM vehicle_tracking
            GROUP BY vehicle_id
        )
    """

    states = {}

    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(query)

        for plate, status, ts in cur.fetchall():
            states[plate] = (status, ts)

    return states
