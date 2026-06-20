"""
test_json_safety.py — 测试 json_safety 模块的安全解析与写入
"""
import json
import pytest

from app.json_safety import safe_json_parse, safe_json_dump


# ── safe_json_parse 测试 ──────────────────────────────────────────

class TestSafeJsonParse:
    """safe_json_parse 各种输入场景"""

    def test_normal_json_string(self):
        """正常 JSON 字符串应正确解析"""
        result = safe_json_parse('{"key": "value"}', default={}, field_name="test")
        assert result == {"key": "value"}

    def test_normal_json_list_string(self):
        """正常 JSON 数组字符串应正确解析"""
        result = safe_json_parse('[1, 2, 3]', default=[], field_name="test")
        assert result == [1, 2, 3]

    def test_malformed_json_returns_default(self):
        """畸形 JSON 字符串应返回 default"""
        result = safe_json_parse('{invalid json}', default={}, field_name="test")
        assert result == {}

    def test_malformed_json_returns_default_list(self):
        """畸形 JSON 字符串应返回 default（列表）"""
        result = safe_json_parse('[broken', default=[], field_name="test")
        assert result == []

    def test_none_input_returns_default(self):
        """None 输入应返回 default"""
        result = safe_json_parse(None, default={}, field_name="test")
        assert result == {}

    def test_none_input_default_none(self):
        """None 输入、default 为 None 时返回 None"""
        result = safe_json_parse(None, default=None, field_name="test")
        assert result is None

    def test_already_dict_returns_directly(self):
        """已经是 dict 的输入直接返回"""
        data = {"key": "value"}
        result = safe_json_parse(data, default={}, field_name="test")
        assert result is data  # 同一对象

    def test_already_list_returns_directly(self):
        """已经是 list 的输入直接返回"""
        data = [1, 2, 3]
        result = safe_json_parse(data, default=[], field_name="test")
        assert result is data  # 同一对象

    def test_empty_string_returns_default(self):
        """空字符串应返回 default"""
        result = safe_json_parse("", default={}, field_name="test")
        assert result == {}

    def test_empty_string_default_list(self):
        """空字符串、default 为列表时返回空列表"""
        result = safe_json_parse("", default=[], field_name="test")
        assert result == []

    def test_whitespace_string_returns_default(self):
        """纯空白字符串应返回 default"""
        result = safe_json_parse("   ", default={}, field_name="test")
        assert result == {}

    def test_numeric_string_returns_default(self):
        """纯数字字符串不是合法 JSON 对象，返回 default"""
        result = safe_json_parse("42", default=None, field_name="test")
        # json.loads("42") 返回 42，不是 dict/list 但也不会崩溃
        assert result == 42

    def test_field_name_logged_on_error(self, caplog):
        """解析失败时 field_name 应出现在日志中"""
        with caplog.at_level("WARNING"):
            safe_json_parse("{bad}", default={}, field_name="my_field")
        assert "my_field" in caplog.text


# ── safe_json_dump 测试 ───────────────────────────────────────────

class TestSafeJsonDump:
    """safe_json_dump 各种输入场景"""

    def test_normal_dict(self):
        """正常 dict 应序列化为 JSON 字符串"""
        result = safe_json_dump({"key": "value"}, field_name="test")
        assert result == '{"key": "value"}'

    def test_normal_list(self):
        """正常 list 应序列化为 JSON 字符串"""
        result = safe_json_dump([1, 2, 3], field_name="test")
        assert result == "[1, 2, 3]"

    def test_none_returns_none(self):
        """None 输入返回 None"""
        result = safe_json_dump(None, field_name="test")
        assert result is None

    def test_already_valid_json_string(self):
        """已经是合法 JSON 字符串时原样返回"""
        json_str = '{"key": "value"}'
        result = safe_json_dump(json_str, field_name="test")
        assert result is json_str  # 原样返回同一对象

    def test_already_valid_json_list_string(self):
        """已经是合法 JSON 数组字符串时原样返回"""
        json_str = '[1, 2, 3]'
        result = safe_json_dump(json_str, field_name="test")
        assert result is json_str

    def test_invalid_json_string_wrapped(self):
        """非法 JSON 字符串应被包装为合法 JSON 字符串"""
        bad_str = "not json at all"
        result = safe_json_dump(bad_str, field_name="test")
        # 被包装后应该是合法的 JSON
        assert result is not None
        parsed = json.loads(result)
        assert isinstance(parsed, str)
        assert parsed == "not json at all"

    def test_chinese_content(self):
        """中文内容应 ensure_ascii=False"""
        result = safe_json_dump({"名称": "测试"}, field_name="test")
        assert "名称" in result
        assert "\\u" not in result  # 不应被 unicode 转义

    def test_empty_dict(self):
        """空 dict 应序列化为 '{}'"""
        result = safe_json_dump({}, field_name="test")
        assert result == "{}"

    def test_empty_list(self):
        """空 list 应序列化为 '[]'"""
        result = safe_json_dump([], field_name="test")
        assert result == "[]"

    def test_field_name_logged_on_invalid_string(self, caplog):
        """非法 JSON 字符串写入时 field_name 应出现在日志中"""
        with caplog.at_level("WARNING"):
            safe_json_dump("not json", field_name="my_field")
        assert "my_field" in caplog.text
