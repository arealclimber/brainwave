#!/usr/bin/env python3
"""
Basic import test for the word count monitoring system
"""

try:
    print("Testing imports...")
    
    # Test NotionService
    from notion_service import notion_service
    print("✓ NotionService imported successfully")
    
    # Test StateManager
    from state_manager import state_manager
    print("✓ StateManager imported successfully")
    
    # Test Monitor
    from monitor import word_count_monitor
    print("✓ WordCountMonitor imported successfully")
    
    # Test basic functionality without API calls
    print("\nTesting basic functionality...")
    
    # Test word counting
    test_text = "Hello world! 這是一個測試。This is a test with 中文 and English."
    word_count = notion_service.count_words(test_text)
    print(f"✓ Word count test: {word_count} words")
    
    # Test state manager
    stats = state_manager.get_stats()
    print(f"✓ State manager stats: {stats}")
    
    # Test monitor status (without starting it)
    status = word_count_monitor.get_status()
    print(f"✓ Monitor status: running={status['running']}")
    
    print("\n✅ All imports and basic functionality tests passed!")
    
except ImportError as e:
    print(f"❌ Import error: {e}")
    exit(1)
except Exception as e:
    print(f"❌ Error: {e}")
    exit(1)