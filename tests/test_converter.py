"""测试 converter.py"""

from minecraft_wiki_mdifier.converter import MarkdownConverter


class TestEncodeCacheValue:
    """_encode_cache_value 测试"""

    def test_encode_never_contains_pipe(self):
        """base64 编码结果中不包含 |，避免分隔符冲突"""
        from minecraft_wiki_mdifier.converter import _encode_cache_value

        # 包含各种特殊字符的值
        test_values = [
            "a|b",
            "x|y|z",
            "key=value",
            "a|b=c|d",
            "{}|[]",
            "中文|english",
        ]
        for v in test_values:
            encoded = _encode_cache_value(v)
            # URL-safe base64 不包含 |，确保分隔符不冲突
            assert "|" not in encoded, f"encoded value should not contain pipe: {encoded}"

    def test_encode_decode_roundtrip(self):
        """编码后能正确还原"""
        from minecraft_wiki_mdifier.converter import _encode_cache_value

        test_values = [
            "simple",
            "a|b|c",
            "key=value",
            "mixed|a=b|normal",
            "123|456|789",
        ]
        for v in test_values:
            # 由于使用 base64，编码后直接解码应该能还原
            import base64

            encoded = _encode_cache_value(v)
            decoded = base64.urlsafe_b64decode(encoded).decode("utf-8")
            assert decoded == v


class TestCancelThreadSafety:
    """cancel() 和 is_cancelled() 线程安全测试"""

    def test_cancel_is_thread_safe(self):
        """cancel() 从多线程并发调用时无数据竞争"""
        import threading

        converter = MarkdownConverter(lang="zh", use_persistent_cache=False)
        converter._cancelled = False  # 重置状态

        call_count = {"cancel": 0, "check": 0}
        results = []

        def cancel_repeatedly():
            for _ in range(100):
                converter.cancel()
                call_count["cancel"] += 1

        def check_cancelled_repeatedly():
            for _ in range(100):
                results.append(converter.is_cancelled())
                call_count["check"] += 1

        threads = [
            threading.Thread(target=cancel_repeatedly),
            threading.Thread(target=cancel_repeatedly),
            threading.Thread(target=check_cancelled_repeatedly),
            threading.Thread(target=check_cancelled_repeatedly),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # 验证 is_cancelled() 至少被调用了预期次数
        assert call_count["check"] == 200
        # cancel 被调用至少一次后，is_cancelled 应该返回 True
        assert converter.is_cancelled() is True
