from app.plugin.module_ai.query.filtering import is_system_table, is_audit_field, DEFAULT_FILTER_RULES

def test_system_table_by_prefix(): assert is_system_table("SYS_USER")
def test_system_table_case(): assert is_system_table("sys_user")
def test_system_table_by_keyword(): assert is_system_table("FUEL_CMCS_X_BAK")
def test_system_table_by_exact(): assert is_system_table("alembic_version")
def test_business_table(): assert not is_system_table("video_cameras")
def test_audit_field(): assert is_audit_field("created_time")
def test_business_field(): assert not is_audit_field("coal_amount")
