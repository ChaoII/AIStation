-- 首次建库时自动启用扩展（仅空数据卷时执行一次）
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_jieba;
CREATE EXTENSION IF NOT EXISTS age;

-- AGE 需要在会话中先 LOAD（且容器以 -c shared_preload_libraries=age 启动）
LOAD 'age';

-- 设置搜索路径，便于使用 age 的 agtype
SET search_path = public, ag_catalog;

-- 示例：创建图
-- SELECT create_graph('kb_graph');
