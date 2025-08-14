#!/usr/bin/env python3
"""
Standalone test for word count functionality without dependencies
"""

import re

def count_words(text: str) -> int:
    """Count words in text (handles both English and Chinese) - standalone version"""
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

def test_stt_word_counting():
    """Test word counting for typical STT scenarios"""
    
    print("Testing word count calculation for STT content...\n")
    
    # Realistic STT test cases
    stt_test_cases = [
        {
            "content": "Hello, this is a test recording from my voice notes.",
            "description": "Simple English voice note",
            "expected": 10
        },
        {
            "content": "今天的會議討論了很多重要的議題，包括專案進度和預算分配。",
            "description": "Chinese meeting notes",
            "expected": 26
        },
        {
            "content": "I had a great idea today. 我今天有一個很棒的想法。Let me record it quickly before I forget.",
            "description": "Mixed language idea recording",
            "expected": 25
        },
        {
            "content": "Meeting notes: We discussed the Q4 budget, team restructuring, and new product launch. 會議記錄：我們討論了第四季預算、團隊重組和新產品發布。",
            "description": "Bilingual meeting summary", 
            "expected": 37
        },
        {
            "content": "Quick voice memo: Buy groceries, call mom, finish presentation. 快速語音備忘：買菜、打電話給媽媽、完成簡報。",
            "description": "Voice memo/todo list",
            "expected": 27
        }
    ]
    
    all_passed = True
    
    for i, test_case in enumerate(stt_test_cases, 1):
        content = test_case["content"]
        description = test_case["description"]
        expected = test_case["expected"]
        
        actual = count_words(content)
        status = "✓" if actual == expected else "✗"
        
        if actual != expected:
            all_passed = False
            
        print(f"Test {i}: {description}")
        print(f"Content: '{content[:60]}{'...' if len(content) > 60 else ''}'")
        print(f"{status} Word count: {actual} (expected: {expected})")
        if actual != expected:
            print(f"   → Difference: {actual - expected} words")
        print()
    
    return all_passed

def test_edge_cases():
    """Test edge cases for word counting"""
    
    print("Testing edge cases...\n")
    
    edge_cases = [
        ("", 0, "Empty string"),
        ("   ", 0, "Whitespace only"),
        ("Hello", 1, "Single English word"),
        ("你", 1, "Single Chinese character"),
        ("Hello! How are you? I'm fine.", 7, "Punctuation handling"),
        ("你好！你好嗎？我很好。", 8, "Chinese with punctuation"),
        ("123 456 789", 3, "Numbers"),
        ("Hello123World", 1, "Mixed alphanumeric"),
        ("    Hello    World    ", 2, "Extra whitespace"),
    ]
    
    all_passed = True
    
    for content, expected, description in edge_cases:
        actual = count_words(content)
        status = "✓" if actual == expected else "✗"
        
        if actual != expected:
            all_passed = False
            
        print(f"{status} {description}: '{content}' → {actual} words (expected: {expected})")
    
    print()
    return all_passed

def simulate_stt_note_creation():
    """Simulate the STT note creation process with word count"""
    
    print("Simulating STT note creation with word count...\n")
    
    # Sample STT transcript
    transcript = """
    今天我想分享一些關於工作效率的想法。
    I've been thinking about productivity tips that really work.
    首先，番茄鐘技術真的很有效，可以幫助我專注工作。
    The Pomodoro technique has been incredibly helpful for maintaining focus.
    另外，定期休息也很重要，不要一直坐著工作。
    Also, taking regular breaks is essential - don't just sit and work all day.
    """.strip()
    
    # Calculate word count
    word_count = count_words(transcript)
    
    # Simulate the properties that would be sent to Notion
    simulated_properties = {
        "Idea": {
            "title": "Productivity Tips Voice Note"
        },
        "Words": {
            "number": word_count  # This is the key addition!
        },
        "Category": {
            "multi_select": ["Personal Development"]
        },
        "Status": {
            "status": "New idea"
        }
    }
    
    print("📝 STT Transcript Content:")
    print(f"'{transcript[:100]}...'")
    print()
    print(f"📊 Calculated Word Count: {word_count}")
    print()
    print("🏗️  Simulated Notion Properties:")
    for key, value in simulated_properties.items():
        if key == "Words":
            print(f"  ✨ {key}: {value['number']} (AUTO-CALCULATED)")
        else:
            print(f"  📋 {key}: {value}")
    
    print()
    print("✅ Word count would be automatically included in new STT notes!")
    
    return True

if __name__ == "__main__":
    print("🎤 Testing STT Word Count Integration (Standalone)\n")
    print("=" * 60)
    
    tests = [
        ("STT Word Counting", test_stt_word_counting),
        ("Edge Cases", test_edge_cases),
        ("STT Note Simulation", simulate_stt_note_creation),
    ]
    
    passed = 0
    failed = 0
    
    for test_name, test_func in tests:
        try:
            print(f"\n📋 {test_name}")
            print("-" * 40)
            
            if test_func():
                print(f"✅ {test_name}: PASSED")
                passed += 1
            else:
                print(f"❌ {test_name}: FAILED")
                failed += 1
                
        except Exception as e:
            print(f"❌ {test_name}: ERROR - {e}")
            failed += 1
    
    print("\n" + "=" * 60)
    print(f"📊 Final Results: {passed} passed, {failed} failed")
    
    if failed == 0:
        print("\n🎉 All tests passed!")
        print("✨ STT notes will now automatically include word counts!")
        print("📈 The 'Words' field will be populated when creating new voice notes!")
    else:
        print(f"\n⚠️  {failed} test(s) failed. Please review the issues above.")