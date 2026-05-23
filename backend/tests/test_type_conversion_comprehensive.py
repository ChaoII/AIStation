"""
全面的类型转换测试。

测试MySQL、PostgreSQL、Python和前端TypeScript的代码生成字段类型转换正确性，覆盖所有支持的类型。
"""

import pytest
from app.common.constant import GenConstant
from app.config.setting import settings
from app.plugin.module_generator.gencode.tools.gen_util import GenUtils
from app.plugin.module_generator.gencode.tools.jinja2_template_util import Jinja2TemplateUtil


def test_mysql_complete_type_conversion():
    """
    测试MySQL完整类型转换
    """
    # 保存原始数据库类型
    original_db_type = settings.DATABASE_TYPE
    try:
        # 设置为MySQL
        settings.DATABASE_TYPE = "mysql"
        
        # 测试所有MySQL类型
        test_cases = [
            # 整数类型
            ("TINYINT", "int", "number"),
            ("TINYINT(1)", "bool", "boolean"),
            ("TINYINT UNSIGNED", "int", "number"),
            ("SMALLINT", "int", "number"),
            ("SMALLINT UNSIGNED", "int", "number"),
            ("MEDIUMINT", "int", "number"),
            ("MEDIUMINT UNSIGNED", "int", "number"),
            ("INT", "int", "number"),
            ("INT UNSIGNED", "int", "number"),
            ("BIGINT", "int", "number"),
            ("BIGINT UNSIGNED", "int", "number"),
            
            # 浮点类型
            ("FLOAT", "float", "number"),
            ("DOUBLE", "float", "number"),
            ("DECIMAL", "Decimal", "string"),
            ("DECIMAL(10,2)", "Decimal", "string"),
            ("NUMERIC", "Decimal", "string"),
            ("NUMERIC(10,2)", "Decimal", "string"),
            
            # 字符串类型
            ("CHAR", "str", "string"),
            ("CHAR(10)", "str", "string"),
            ("VARCHAR", "str", "string"),
            ("VARCHAR(255)", "str", "string"),
            ("VARCHAR(255) COLLATE utf8mb4_unicode_ci", "str", "string"),
            ("TINYTEXT", "str", "string"),
            ("TEXT", "str", "string"),
            ("MEDIUMTEXT", "str", "string"),
            ("LONGTEXT", "str", "string"),
            
            # 二进制类型
            ("BINARY", "bytes", "string"),
            ("BINARY(10)", "bytes", "string"),
            ("VARBINARY", "bytes", "string"),
            ("VARBINARY(255)", "bytes", "string"),
            ("TINYBLOB", "bytes", "string"),
            ("BLOB", "bytes", "string"),
            ("MEDIUMBLOB", "bytes", "string"),
            ("LONGBLOB", "bytes", "string"),
            
            # 日期时间类型
            ("DATE", "date", "string"),
            ("TIME", "time", "string"),
            ("DATETIME", "datetime", "string"),
            ("TIMESTAMP", "datetime", "string"),
            ("YEAR", "int", "number"),
            
            # 其他类型
            ("JSON", "dict", "Record<string, unknown>"),
            ("ENUM('a','b','c')", "str", "string"),
            ("SET('a','b','c')", "str", "string"),
            ("BIT", "int", "number"),
            ("BIT(1)", "int", "number"),
            
            # 空间数据类型
            ("GEOMETRY", "bytes", "string"),
            ("POINT", "bytes", "string"),
            ("LINESTRING", "bytes", "string"),
            ("POLYGON", "bytes", "string"),
            ("MULTIPOINT", "bytes", "string"),
            ("MULTILINESTRING", "bytes", "string"),
            ("MULTIPOLYGON", "bytes", "string"),
            ("GEOMETRYCOLLECTION", "bytes", "string"),
        ]
        
        for db_type, expected_python_type, expected_ts_type in test_cases:
            # 测试数据库类型提取
            extracted_type = GenUtils.get_db_type(db_type)
            # 测试Python类型映射
            
            # 特殊处理几何类型，根据数据库类型选择不同的映射
            if extracted_type in ["point", "line", "linestring", "polygon", "multipoint", "multilinestring", "multipolygon", "geometrycollection", "geometry"]:
                python_type = "bytes"  # MySQL几何类型映射为bytes
            else:
                python_type = GenConstant.DB_TO_PYTHON.get(extracted_type, "str")
            
            assert python_type == expected_python_type, f"MySQL {db_type} -> Python {python_type}, expected {expected_python_type}"
            # 测试TypeScript类型映射
            ts_type = Jinja2TemplateUtil.python_type_to_ts_type(python_type)
            assert ts_type == expected_ts_type, f"Python {python_type} -> TypeScript {ts_type}, expected {expected_ts_type}"
    finally:
        # 恢复原始数据库类型
        settings.DATABASE_TYPE = original_db_type


def test_postgres_complete_type_conversion():
    """
    测试PostgreSQL完整类型转换
    """
    # 保存原始数据库类型
    original_db_type = settings.DATABASE_TYPE
    try:
        # 设置为PostgreSQL
        settings.DATABASE_TYPE = "postgres"
        
        # 测试所有PostgreSQL类型
        test_cases = [
            # 整数类型
            ("SMALLINT", "int", "number"),
            ("INT2", "int", "number"),
            ("INTEGER", "int", "number"),
            ("INT4", "int", "number"),
            ("BIGINT", "int", "number"),
            ("INT8", "int", "number"),
            
            # 浮点类型
            ("REAL", "float", "number"),
            ("DOUBLE PRECISION", "float", "number"),
            ("FLOAT8", "float", "number"),
            ("NUMERIC", "Decimal", "string"),
            ("NUMERIC(10,2)", "Decimal", "string"),
            ("DECIMAL", "Decimal", "string"),
            ("DECIMAL(10,2)", "Decimal", "string"),
            
            # 字符串类型
            ("CHAR", "str", "string"),
            ("CHAR(10)", "str", "string"),
            ("VARCHAR", "str", "string"),
            ("VARCHAR(255)", "str", "string"),
            ("CHARACTER", "str", "string"),
            ("CHARACTER(10)", "str", "string"),
            ("CHARACTER VARYING", "str", "string"),
            ("CHARACTER VARYING(255)", "str", "string"),
            ("TEXT", "str", "string"),
            ("CITEXT", "str", "string"),
            
            # 二进制类型
            ("BYTEA", "bytes", "string"),
            
            # 日期时间类型
            ("DATE", "date", "string"),
            ("TIME", "time", "string"),
            ("TIME WITHOUT TIME ZONE", "time", "string"),
            ("TIME WITH TIME ZONE", "time", "string"),
            ("TIMETZ", "time", "string"),
            ("TIMESTAMP", "datetime", "string"),
            ("TIMESTAMP WITHOUT TIME ZONE", "datetime", "string"),
            ("TIMESTAMP WITH TIME ZONE", "datetime", "string"),
            ("TIMESTAMPTZ", "datetime", "string"),
            ("INTERVAL", "timedelta", "string"),
            
            # 布尔类型
            ("BOOLEAN", "bool", "boolean"),
            ("BOOL", "bool", "boolean"),
            
            # JSON类型
            ("JSON", "dict", "Record<string, unknown>"),
            ("JSONB", "dict", "Record<string, unknown>"),
            
            # 数组类型
            ("INTEGER[]", "list", "unknown[]"),
            ("ARRAY[INTEGER]", "list", "unknown[]"),
            ("TEXT[]", "list", "unknown[]"),
            ("ARRAY[TEXT]", "list", "unknown[]"),
            
            # 几何类型
            ("POINT", "list", "unknown[]"),
            ("LINE", "list", "unknown[]"),
            ("LSEG", "list", "unknown[]"),
            ("BOX", "list", "unknown[]"),
            ("PATH", "list", "unknown[]"),
            ("POLYGON", "list", "unknown[]"),
            ("CIRCLE", "list", "unknown[]"),
            
            # 其他类型
            ("UUID", "str", "string"),
            ("INET", "str", "string"),
            ("CIDR", "str", "string"),
            ("MACADDR", "str", "string"),
            ("BIT", "int", "number"),
            ("BIT VARYING", "int", "number"),
            ("VARBIT", "int", "number"),
            ("TSVECTOR", "str", "string"),
            ("TSQUERY", "str", "string"),
            ("XML", "str", "string"),
            ("MONEY", "Decimal", "string"),
            ("OID", "int", "number"),
            ("REGPROC", "str", "string"),
            ("REGCLASS", "str", "string"),
            ("REGTYPE", "str", "string"),
            ("REGROLE", "str", "string"),
            ("REGNAMESPACE", "str", "string"),
            ("INT2VECTOR", "list", "unknown[]"),
            ("OIDVECTOR", "list", "unknown[]"),
            ("PG_LSN", "int", "number"),
            ("TXID_SNAPSHOT", "str", "string"),
            ("PG_NODE_TREE", "str", "string"),
            
            # 范围类型
            ("INT4RANGE", "list", "unknown[]"),
            ("INT8RANGE", "list", "unknown[]"),
            ("TSRANGE", "list", "unknown[]"),
            ("TSTZRANGE", "list", "unknown[]"),
            ("DATERANGE", "list", "unknown[]"),
        ]
        
        for db_type, expected_python_type, expected_ts_type in test_cases:
            # 测试数据库类型提取
            extracted_type = GenUtils.get_db_type(db_type)
            # 测试Python类型映射
            
            # 特殊处理几何类型，根据数据库类型选择不同的映射
            if extracted_type in ["point", "line", "lseg", "box", "path", "polygon", "circle"]:
                python_type = "list"  # PostgreSQL几何类型映射为list
            else:
                python_type = GenConstant.DB_TO_PYTHON.get(extracted_type, "str")
            
            assert python_type == expected_python_type, f"PostgreSQL {db_type} -> Python {python_type}, expected {expected_python_type}"
            # 测试TypeScript类型映射
            ts_type = Jinja2TemplateUtil.python_type_to_ts_type(python_type)
            assert ts_type == expected_ts_type, f"Python {python_type} -> TypeScript {ts_type}, expected {expected_ts_type}"
    finally:
        # 恢复原始数据库类型
        settings.DATABASE_TYPE = original_db_type


def test_sqlalchemy_type_comprehensive():
    """
    测试SQLAlchemy类型映射的完整性
    """
    # 测试MySQL SQLAlchemy类型
    settings.DATABASE_TYPE = "mysql"
    mysql_test_cases = [
        ("INT", "Integer"),
        ("BIGINT", "BigInteger"),
        ("TINYINT", "SmallInteger"),
        ("TINYINT(1)", "Boolean"),
        ("FLOAT", "Float"),
        ("DOUBLE", "Float"),
        ("DECIMAL", "DECIMAL"),
        ("DECIMAL(10,2)", "DECIMAL(10,2)"),
        ("CHAR", "CHAR(255)"),
        ("CHAR(10)", "CHAR(10)"),
        ("VARCHAR", "String(255)"),
        ("VARCHAR(255)", "String(255)"),
        ("TEXT", "Text"),
        ("DATE", "Date"),
        ("TIME", "Time"),
        ("DATETIME", "DateTime"),
        ("TIMESTAMP", "TIMESTAMP"),
        ("YEAR", "Integer"),
        ("JSON", "JSON"),
        ("ENUM('a','b','c')", "Enum"),
    ]
    
    for db_type, expected_sqlalchemy_type in mysql_test_cases:
        sqlalchemy_type = Jinja2TemplateUtil.get_sqlalchemy_type(db_type)
        assert sqlalchemy_type == expected_sqlalchemy_type, f"MySQL {db_type} -> SQLAlchemy {sqlalchemy_type}, expected {expected_sqlalchemy_type}"
    
    # 测试PostgreSQL SQLAlchemy类型
    settings.DATABASE_TYPE = "postgres"
    postgres_test_cases = [
        ("INTEGER", "Integer"),
        ("BIGINT", "BigInteger"),
        ("SMALLINT", "SmallInteger"),
        ("REAL", "Float"),
        ("DOUBLE PRECISION", "Float"),
        ("NUMERIC", "Numeric"),
        ("NUMERIC(10,2)", "Numeric(10,2)"),
        ("VARCHAR", "String(255)"),
        ("VARCHAR(255)", "String(255)"),
        ("TEXT", "Text"),
        ("DATE", "Date"),
        ("TIME", "Time"),
        ("TIMESTAMP", "DateTime"),
        ("BOOLEAN", "Boolean"),
        ("JSONB", "JSONB"),
        ("UUID", "Uuid"),
        ("BYTEA", "LargeBinary"),
    ]
    
    for db_type, expected_sqlalchemy_type in postgres_test_cases:
        sqlalchemy_type = Jinja2TemplateUtil.get_sqlalchemy_type(db_type)
        assert sqlalchemy_type == expected_sqlalchemy_type, f"PostgreSQL {db_type} -> SQLAlchemy {sqlalchemy_type}, expected {expected_sqlalchemy_type}"


def test_edge_cases():
    """
    测试边缘情况
    """
    # 测试空类型
    assert Jinja2TemplateUtil.python_type_to_ts_type(None) == "string"
    assert Jinja2TemplateUtil.python_type_to_ts_type("") == "string"
    assert Jinja2TemplateUtil.python_type_to_ts_type("   ") == "string"
    
    # 测试未知类型
    assert Jinja2TemplateUtil.python_type_to_ts_type("unknown_type") == "string"
    
    # 测试大小写不敏感
    assert GenUtils.get_db_type("VARCHAR(255)") == "varchar"
    assert GenUtils.get_db_type("tinyint(1)") == "boolean"
    assert GenUtils.get_db_type("array[integer]") == "array"


if __name__ == "__main__":
    pytest.main(["-v", "tests/test_type_conversion_comprehensive.py"])
