# 一体化 PostgreSQL 18 镜像（基于官方 pgvector 基础镜像，不再重编 pgvector）
#
# 基础镜像：pgvector/pgvector:0.8.1-pg18-trixie（Postgres 18 + pgvector 0.8.1）
# 在其上仅叠加：
#   - pg_jieba  v2.0.1（中文分词全文检索，CMake 构建）
#   - Apache AGE PG18 / 1.7.0（图数据库扩展，make 构建）
#
# 构建：
#   docker build -f devops/postgres/Dockerfile -t aistation-pg-rag:18 .
#   可覆盖基础镜像/版本：
#   --build-arg BASE_IMAGE=pgvector/pgvector:0.8.6-pg18
#   --build-arg PGJIEBA_VERSION=2.0.1
#   --build-arg AGE_BRANCH=PG18
#
# 注意：AGE 需要 shared_preload_libraries=age（镜像默认启动参数已带）。

ARG BASE_IMAGE=pgvector/pgvector:0.8.6-pg18-trixie
FROM ${BASE_IMAGE}

ARG PGJIEBA_VERSION=2.0.1
ARG AGE_BRANCH=PG18

# 构建依赖（PG18 server-dev + CMake/jieba/AGE 所需）
# git 源码走 ghfast.top 加速；Debian apt 源改为中科大镜像
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        curl ca-certificates gnupg \
        build-essential git cmake flex bison gawk \
        libreadline-dev zlib1g-dev pkg-config \
        postgresql-server-dev-18 \
    && rm -rf /var/lib/apt/lists/* \
    && sed -i 's@deb.debian.org@mirrors.ustc.edu.cn@g; s@security.debian.org@mirrors.ustc.edu.cn@g' \
        /etc/apt/sources.list.d/debian.sources \
    && apt-get update \
    && apt-get install -y --no-install-recommends postgresql-server-dev-18 \
    && rm -rf /var/lib/apt/lists/*

# 让所有 GitHub 拉取（含子模块）走 ghfast.top 加速
RUN git config --global url."https://ghfast.top/https://github.com/".insteadOf "https://github.com/"

# ---------- pg_jieba（中文分词全文检索，CMake 构建） ----------
RUN git clone --branch "v${PGJIEBA_VERSION}" --depth 1 \
        https://ghfast.top/https://github.com/jaiminpan/pg_jieba.git /src/pg_jieba \
    && cd /src/pg_jieba \
    && git submodule update --init --recursive --jobs 4 \
    && cmake -B build -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_CXX_FLAGS="-I/usr/include/postgresql/18/server" \
    && cmake --build build -j"$(nproc)" \
    && cmake --install build \
    && rm -rf /src/pg_jieba

# ---------- Apache AGE（图数据库扩展，make 构建） ----------
RUN git clone --branch "${AGE_BRANCH}" --depth 1 \
        https://ghfast.top/https://github.com/apache/age.git /src/age \
    && cd /src/age \
    && { make clean >/dev/null 2>&1 || true; } \
    && make -s \
    && make install \
    && rm -rf /src/age

# 首次建库自动启用扩展
COPY init-extensions.sql /docker-entrypoint-initdb.d/10-init-extensions.sql

# 默认启用 AGE + pg_jieba 为共享预加载扩展（可用容器参数覆盖）
CMD ["postgres", "-c", "shared_preload_libraries=age,pg_jieba"]
