from db.schema import get_connection

with get_connection() as conn:
    rows = conn.execute(
        "SELECT game_date, dnp FROM game_logs WHERE player_name = 'Ajay Mitchell'"
    ).fetchall()
    print([dict(r) for r in rows])
print("done")
