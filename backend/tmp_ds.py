import psycopg

conn = psycopg.connect("host=127.0.0.1 port=5432 user=root password=ServBay.dev dbname=aistation")
cur = conn.cursor()
cur.execute('SELECT id,code,name,type,host,database FROM ai_query_datasources WHERE is_deleted=false ORDER BY id')
print("=== 数据源 ===")
for r in cur.fetchall():
    print(r)
cur.execute("SELECT COUNT(*) FROM ai_query_schema")
print("已同步表总数:", cur.fetchone()[0])
cur.execute("SELECT datasource, COUNT(*) FROM ai_query_schema GROUP BY datasource")
print("各源同步表数:", cur.fetchall())
