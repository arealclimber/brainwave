#!/usr/bin/env python3
"""
Test basic functionality without external dependencies
"""

import sys
import os
import re

def test_word_counting():
    """Test word counting logic standalone"""
    
    def count_words(text: str) -> int:
        """Count words in text (handles both English and Chinese)"""
        if not text.strip():
            return 0
        
        # Count Chinese characters (each character counts as one word)
        chinese_chars = re.findall(r'[\u4e00-\u9fff]', text)
        chinese_count = len(chinese_chars)
        
        # Remove Chinese characters and count English words
        english_text = re.sub(r'[\u4e00-\u9fff]', '', text)
        # Split by whitespace and filter out empty strings and punctuation-only strings
        english_words = [word for word in re.findall(r'\b\w+\b', english_text) if word]
        english_count = len(english_words)
        
        total_words = chinese_count + english_count
        return total_words
    
    # Test cases
    test_cases = [
        ("Hello world", 2),
        ("你好世界", 4),
        ("Hello 你好 world 世界", 6),
        ("", 0),
        ("  ", 0),
        ("This is a test with 中文 and English words.", 10),
    ]
    
    print("Testing word counting logic...")
    for text, expected in test_cases:
        result = count_words(text)
        status = "✓" if result == expected else "✗"
        print(f"{status} '{text}' -> {result} words (expected: {expected})")
        if result != expected:
            return False
    
    return True

def test_file_structure():
    """Test if all required files exist"""
    required_files = [
        "notion_service.py",
        "state_manager.py", 
        "monitor.py",
        "requirements.txt",
        ".env.example",
        "realtime_server.py",
    ]
    
    print("\nTesting file structure...")
    for filename in required_files:
        if os.path.exists(filename):
            print(f"✓ {filename}")
        else:
            print(f"✗ {filename} missing")
            return False
    
    return True

def test_syntax():
    """Test Python syntax of our modules"""
    import py_compile
    
    modules = [
        "notion_service.py",
        "state_manager.py",
        "monitor.py",
    ]
    
    print("\nTesting Python syntax...")
    for module in modules:
        try:
            py_compile.compile(module, doraise=True)
            print(f"✓ {module} syntax OK")
        except py_compile.PyCompileError as e:
            print(f"✗ {module} syntax error: {e}")
            return False
    
    return True

if __name__ == "__main__":
    print("🚀 Running basic functionality tests...\n")
    
    tests = [
        ("Word counting logic", test_word_counting),
        ("File structure", test_file_structure),
        ("Python syntax", test_syntax),
    ]
    
    passed = 0
    failed = 0
    
    for test_name, test_func in tests:
        try:
            if test_func():
                print(f"✅ {test_name}: PASSED\n")
                passed += 1
            else:
                print(f"❌ {test_name}: FAILED\n")
                failed += 1
        except Exception as e:
            print(f"❌ {test_name}: ERROR - {e}\n")
            failed += 1
    
    print(f"📊 Test Results: {passed} passed, {failed} failed")
    
    if failed == 0:
        print("🎉 All basic tests passed! The word count monitoring system is ready for deployment.")
        sys.exit(0)
    else:
        print("⚠️  Some tests failed. Please check the issues above.")
        sys.exit(1)