"""
类型转换测试。

测试MySQL、PostgreSQL、Python和前端TypeScript的代码生成字段类型转换正确性。
"""

import pytest
from app.common.constant import GenConstant
from app.config.setting import settings
from app.plugin.module_generator.gencode.tools.gen_util import GenUtils
from app.plugin.module_generator.gencode.tools.jinja2_template_util import Jinja2TemplateUtil


def test_mysql_type_conversion():
    """
    测试MySQL类型转换
    """
    # 保存原始数据库类型
    original_db_type = settings.DATABASE_TYPE
    try:
        # 设置为MySQL
        settings.DATABASE_TYPE = "mysql"
        
        # 测试MySQL类型
        test_cases = [
            # (数据库类型, 期望的Python类型, 期望的TypeScript类型)
            ("INT", "int", "number"),
            ("BIGINT", "int", "number"),
            ("TINYINT", "int", "number"),
            ("TINYINT(1)", "bool", "boolean"),
            ("FLOAT", "float", "number"),
            ("DOUBLE", "float", "number"),
            ("DECIMAL(10,2)", "Decimal", "string"),
            ("CHAR(10)", "str", "string"),
            ("VARCHAR(255)", "str", "string"),
            ("TEXT", "str", "string"),
            ("DATE", "date", "string"),
            ("TIME", "time", "string"),
            ("DATETIME", "datetime", "string"),
            ("TIMESTAMP", "datetime", "string"),
            ("YEAR", "int", "number"),
            ("JSON", "dict", "Record<string, unknown>"),
            ("ENUM('a','b','c')", "str", "string"),
        ]
        
        for db_type, expected_python_type, expected_ts_type in test_cases:
            # 测试数据库类型提取
            extracted_type = GenUtils.get_db_type(db_type)
            # 测试Python类型映射
            python_type = GenConstant.DB_TO_PYTHON.get(extracted_type, "str")
            assert python_type == expected_python_type, f"MySQL {db_type} -> Python {python_type}, expected {expected_python_type}"
            # 测试TypeScript类型映射
            ts_type = Jinja2TemplateUtil.python_type_to_ts_type(python_type)
            assert ts_type == expected_ts_type, f"Python {python_type} -> TypeScript {ts_type}, expected {expected_ts_type}"
    finally:
        # 恢复原始数据库类型
        settings.DATABASE_TYPE = original_db_type


def test_postgres_type_conversion():
    """
    测试PostgreSQL类型转换
    """
    # 保存原始数据库类型
    original_db_type = settings.DATABASE_TYPE
    try:
        # 设置为PostgreSQL
        settings.DATABASE_TYPE = "postgres"
        
        # 测试PostgreSQL类型
        test_cases = [
            # (数据库类型, 期望的Python类型, 期望的TypeScript类型)
            ("INTEGER", "int", "number"),
            ("BIGINT", "int", "number"),
            ("SMALLINT", "int", "number"),
            ("REAL", "float", "number"),
            ("DOUBLE PRECISION", "float", "number"),
            ("NUMERIC(10,2)", "Decimal", "string"),
            ("VARCHAR(255)", "str", "string"),
            ("CHAR(10)", "str", "string"),
            ("TEXT", "str", "string"),
            ("DATE", "date", "string"),
            ("TIME", "time", "string"),
            ("TIMESTAMP", "datetime", "string"),
            ("TIMESTAMP WITH TIME ZONE", "datetime", "string"),
            ("BOOLEAN", "bool", "boolean"),
            ("JSONB", "dict", "Record<string, unknown>"),
            ("UUID", "str", "string"),
            ("ARRAY[INTEGER]", "list", "unknown[]"),
            ("POINT", "list", "unknown[]"),
        ]
        
        for db_type, expected_python_type, expected_ts_type in test_cases:
            # 测试数据库类型提取
            extracted_type = GenUtils.get_db_type(db_type)
            # 测试Python类型映射
            python_type = GenConstant.DB_TO_PYTHON.get(extracted_type, "str")
            assert python_type == expected_python_type, f"PostgreSQL {db_type} -> Python {python_type}, expected {expected_python_type}"
            # 测试TypeScript类型映射
            ts_type = Jinja2TemplateUtil.python_type_to_ts_type(python_type)
            assert ts_type == expected_ts_type, f"Python {python_type} -> TypeScript {ts_type}, expected {expected_ts_type}"
    finally:
        # 恢复原始数据库类型
        settings.DATABASE_TYPE = original_db_type


def test_special_type_handling():
    """
    测试特殊类型处理
    """
    # 测试tinyint(1)特殊处理
    assert GenUtils.get_db_type("TINYINT(1)") == "boolean"
    
    # 测试数组类型处理
    assert GenUtils.get_db_type("INTEGER[]") == "array"
    assert GenUtils.get_db_type("TEXT[]") == "array"
    
    # 测试带COLLATE的类型
    assert GenUtils.get_db_type("VARCHAR(255) COLLATE utf8mb4_unicode_ci") == "varchar"
    
    # 测试带UNSIGNED的类型
    assert GenUtils.get_db_type("INT UNSIGNED") == "int"


def test_sqlalchemy_type_mapping():
    """
    测试SQLAlchemy类型映射
    """
    # 测试MySQL SQLAlchemy类型
    settings.DATABASE_TYPE = "mysql"
    assert Jinja2TemplateUtil.get_sqlalchemy_type("INT") == "Integer"
    assert Jinja2TemplateUtil.get_sqlalchemy_type("VARCHAR(255)") == "String(255)"
    assert Jinja2TemplateUtil.get_sqlalchemy_type("TINYINT(1)") == "Boolean"
    
    # 测试PostgreSQL SQLAlchemy类型
    settings.DATABASE_TYPE = "postgres"
    assert Jinja2TemplateUtil.get_sqlalchemy_type("INTEGER") == "Integer"
    assert Jinja2TemplateUtil.get_sqlalchemy_type("VARCHAR(255)") == "String(255)"
    assert Jinja2TemplateUtil.get_sqlalchemy_type("BOOLEAN") == "Boolean"


if __name__ == "__main__":
    pytest.main(["-v", "tests/test_type_conversion.py"])
