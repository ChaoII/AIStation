"""回填知识库分块引用溯源字段（document_id / start_line）。

对指定知识库中缺失溯源的旧分块，按其 file_name 关联文档记录；
若该文件无文档记录则创建一条（拼接分块为 content），再用 content 定位
每个分块的起始行并回填。新上传的文档已有完整溯源，不会重复处理。

用法:  uv run python -m scripts.backfill_knowledge_trace --kb 4
"""
import argparse
import asyncio
import uuid
from datetime import datetime

import asyncpg


async def backfill(conn, kb_id: int) -> dict:
    docs = await conn.fetch(
        "SELECT id, name, content FROM ai_knowledge_documents "
        "WHERE knowledge_base_id=$1 AND is_deleted=false",
        kb_id,
    )
    doc_by_name = {d["name"]: d for d in docs}
    rows = await conn.fetch(
        "SELECT id, file_name, content, chunk_index, document_id "
        "FROM ai_knowledge_chunks "
        "WHERE knowledge_base_id=$1 AND is_deleted=false AND file_name IS NOT NULL "
        "ORDER BY file_name, chunk_index",
        kb_id,
    )
    groups: dict[str, list] = {}
    for r in rows:
        groups.setdefault(r["file_name"], []).append(r)

    updated = created = 0
    for fname, chs in groups.items():
        doc = doc_by_name.get(fname)
        if doc is None:
            content = "\n\n".join(c["content"] for c in chs)
            doc_id = await conn.fetchval(
                "INSERT INTO ai_knowledge_documents "
                "(uuid, status, created_time, updated_time, is_deleted, deleted_time, "
                " knowledge_base_id, name, file_type, size, content, chunk_count, doc_status) "
                "VALUES ($1,'0',$2,$2,false,NULL,$3,$4,'md',$5,$6,$7,'ready') RETURNING id",
                uuid.uuid4().hex,
                datetime.now(),
                kb_id,
                fname,
                len(content.encode()),
                content,
                len(chs),
            )
            created += 1
        else:
            doc_id = doc["id"]
            content = doc["content"] or "\n\n".join(c["content"] for c in chs)
        for c in chs:
            if c["document_id"]:
                continue
            idx = content.find(c["content"])
            line = content[:idx].count("\n") + 1 if idx >= 0 else None
            await conn.execute(
                "UPDATE ai_knowledge_chunks SET document_id=$1, start_line=$2 WHERE id=$3",
                doc_id,
                line,
                c["id"],
            )
            updated += 1
    return {"kb": kb_id, "created_docs": created, "backfilled_chunks": updated}


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kb", type=int, required=True, help="知识库 ID")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=5432)
    parser.add_argument("--user", default="root")
    parser.add_argument("--password", default="ServBay.dev")
    parser.add_argument("--db", default="aistation")
    args = parser.parse_args()
    conn = await asyncpg.connect(
        user=args.user, password=args.password, host=args.host,
        port=args.port, database=args.db,
    )
    try:
        print(await backfill(conn, args.kb))
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
