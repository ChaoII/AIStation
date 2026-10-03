# 一体化 PostgreSQL 18 镜像：pgvector + pg_jieba + Apache AGE
#
# 用途：AI 知识库 RAG 所需的「向量检索(pgvector) + 中文分词全文检索(pg_jieba) + 图数据库(AGE)」。
#
# 构建：
#   docker build -f devops/postgres/Dockerfile -t aistation-pg-rag:18 .
#
# 版本（可在构建时覆盖）：
#   --build-arg PGVECTOR_VERSION=0.8.6
#   --build-arg PGJIEBA_VERSION=2.0.1
#   --build-arg AGE_VERSION=PG18      # PG18 分支对应 Apache AGE 1.7.0
#
# 注意：
#   - AGE 需要 shared_preload_libraries。镜像默认以 -c shared_preload_libraries=age 启动；
#     也可在 postgresql.conf 写入 `shared_preload_libraries = 'age'`。
#   - 键/向量字段大小写在 PG18 需按需调整（本镜像仅装扩展，不强制迁移）。

FROM postgres:18-bookworm

ARG PGVECTOR_VERSION=0.8.6
ARG PGJIEBA_VERSION=2.0.1
ARG AGE_VERSION=PG18

# 构建依赖（含 PGDG 的 postgresql-server-dev-18）
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential git flex bison \
        libreadline-dev zlib1g-dev pkg-config ca-certificates \
        postgresql-server-dev-18 \
    && rm -rf /var/lib/apt/lists/*

# ---------- pgvector ----------
RUN git clone --branch "v${PGVECTOR_VERSION}" --depth 1 \
        https://github.com/pgvector/pgvector.git /src/pgvector \
    && cd /src/pgvector \
    && { make clean >/dev/null 2>&1 || true; } \
    && make -s \
    && make install \
    && rm -rf /src/pgvector

# ---------- pg_jieba（中文分词全文检索） ----------
RUN git clone --branch "v${PGJIEBA_VERSION}" --depth 1 \
        https://github.com/jaiminpan/pg_jieba.git /src/pg_jieba \
    && cd /src/pg_jieba \
    && git submodule update --init --recursive \
    && { make clean >/dev/null 2>&1 || true; } \
    && make -s \
    && make install \
    && rm -rf /src/pg_jieba

# ---------- Apache AGE（图数据库扩展） ----------
# AGE 按 PG 版本以 git 分支维护（PG18 分支对应 1.7.0）。
RUN git clone --branch "${AGE_VERSION}" --depth 1 \
        https://github.com/apache/age.git /src/age \
    && cd /src/age \
    && { make clean >/dev/null 2>&1 || true; } \
    && make -s \
    && make install \
    && rm -rf /src/age

# 首次建库自动启用扩展
COPY init-extensions.sql /docker-entrypoint-initdb.d/10-init-extensions.sql

# 默认启用 AGE 为共享预加载扩展（可用容器参数覆盖）
CMD ["postgres", "-c", "shared_preload_libraries=age"]
