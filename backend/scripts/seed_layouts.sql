-- 插入示例布局数据
-- 运行: psql -h localhost -U postgres -d fastapi_admin -f scripts/seed_layouts.sql
INSERT INTO video_layouts (uuid, name, grid_type, layout_config, is_default, is_template, patrol_interval, description, status, created_time, updated_time)
SELECT * FROM (VALUES
  (md5(random()::text || clock_timestamp()::text), '主监控室', '4', '{"grid_type":"4","windows":{}}'::jsonb, false, true, 30, '主监控室默认4路分割布局，轮巡周期30秒', '0', NOW(), NOW()),
  (md5(random()::text || clock_timestamp()::text), '仓库全景', '9', '{"grid_type":"9","windows":{}}'::jsonb, true, false, 15, '仓库区域9路全景监控，快速轮巡', '0', NOW(), NOW()),
  (md5(random()::text || clock_timestamp()::text), '出入口特写', '1', '{"grid_type":"1","windows":{}}'::jsonb, false, true, NULL, '单路全屏显示入口摄像机', '0', NOW(), NOW()),
  (md5(random()::text || clock_timestamp()::text), '生产线监控', '6', '{"grid_type":"6","windows":{}}'::jsonb, false, true, 60, '6路重点设备监控，含主画面放大', '0', NOW(), NOW()),
  (md5(random()::text || clock_timestamp()::text), '停车场布局', '16', '{"grid_type":"16","windows":{}}'::jsonb, false, false, 20, '停车场16路密集监控', '0', NOW(), NOW()),
  (md5(random()::text || clock_timestamp()::text), '核心区域', '13', '{"grid_type":"13","windows":{}}'::jsonb, false, true, 10, '13路布局，中间4格合并显示重点区域', '0', NOW(), NOW())
) AS t(uuid, name, grid_type, layout_config, is_default, is_template, patrol_interval, description, status, created_time, updated_time)
WHERE NOT EXISTS (SELECT 1 FROM video_layouts LIMIT 1);
