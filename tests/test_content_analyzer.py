import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from content_analyzer import ContentAnalyzer

class TestContentAnalyzer:
    
    def test_init_success(self):
        """Test ContentAnalyzer initialization success"""
        with patch('content_analyzer.get_llm_processor') as mock_get_processor:
            mock_processor = MagicMock()
            mock_get_processor.return_value = mock_processor
            
            analyzer = ContentAnalyzer()
            assert analyzer.enabled is True
            assert analyzer.model == "gemini-2.5-pro"
            mock_get_processor.assert_called_once_with("gemini")
    
    def test_init_failure(self):
        """Test ContentAnalyzer initialization failure"""
        with patch('content_analyzer.get_llm_processor') as mock_get_processor:
            mock_get_processor.side_effect = Exception("Failed to initialize")
            
            analyzer = ContentAnalyzer()
            assert analyzer.enabled is False
            assert analyzer.llm_processor is None
    
    @pytest.mark.asyncio
    async def test_analyze_content_disabled(self):
        """Test content analysis when analyzer is disabled"""
        with patch('content_analyzer.get_llm_processor') as mock_get_processor:
            mock_get_processor.side_effect = Exception("Failed")
            
            analyzer = ContentAnalyzer()
            result = await analyzer.analyze_content("test content")
            
            # Should return fallback analysis
            assert result["title"] == "test content"
            assert result["category"] == "General"
            assert result["confidence"] == 0.3
            assert result["tags"] == []
    
    @pytest.mark.asyncio
    async def test_analyze_content_success(self):
        """Test successful content analysis"""
        with patch('content_analyzer.get_llm_processor') as mock_get_processor:
            mock_processor = AsyncMock()
            mock_get_processor.return_value = mock_processor
            
            # Mock the async generator responses for different analysis tasks
            async def mock_process_text(content, prompt, model=None):
                if "title" in prompt.lower():
                    yield "Test Analysis Title"
                elif "summary" in prompt.lower():
                    yield "This is a test summary of the content."
                elif "categoriz" in prompt.lower():
                    yield "Technology"
                elif "tag" in prompt.lower():
                    yield "test, analysis, content"
                elif "topic" in prompt.lower():
                    yield "machine learning, artificial intelligence"
                elif "sentiment" in prompt.lower():
                    yield "positive"
                else:
                    yield "default response"
            
            mock_processor.process_text = mock_process_text
            
            analyzer = ContentAnalyzer()
            result = await analyzer.analyze_content("This is test content about AI and machine learning.")
            
            assert result["title"] == "Test Analysis Title"
            assert result["summary"] == "This is a test summary of the content."
            assert result["category"] == "Technology"
            assert result["tags"] == ["test", "analysis", "content"]
            assert result["key_topics"] == ["machine learning", "artificial intelligence"]
            assert result["sentiment"] == "positive"
            assert result["confidence"] > 0.5
    
    def test_extract_category_from_response(self):
        """Test category extraction from response"""
        analyzer = ContentAnalyzer()
        
        # Test successful category detection
        response = "This content is about Technology and programming"
        category = analyzer._extract_category_from_response(response)
        assert category == "Technology"
        
        # Test unknown category defaults to General
        response = "This is about something completely unknown"
        category = analyzer._extract_category_from_response(response)
        assert category == "General"
    
    def test_parse_tags_from_response(self):
        """Test tag parsing from response"""
        analyzer = ContentAnalyzer()
        
        # Test comma-separated tags
        response = "programming, python, machine learning, ai"
        tags = analyzer._parse_tags_from_response(response)
        assert len(tags) == 4
        assert "programming" in tags
        assert "python" in tags
        
        # Test bullet point tags
        response = "• programming\n• python\n• machine learning"
        tags = analyzer._parse_tags_from_response(response)
        assert len(tags) >= 2
        
        # Test numbered tags
        response = "1. programming\n2. python\n3. ai"
        tags = analyzer._parse_tags_from_response(response)
        assert len(tags) >= 2
    
    def test_parse_topics_from_response(self):
        """Test topic parsing from response"""
        analyzer = ContentAnalyzer()
        
        # Test comma-separated topics
        response = "artificial intelligence, machine learning, neural networks"
        topics = analyzer._parse_topics_from_response(response)
        assert len(topics) == 3
        assert "artificial intelligence" in topics
        
        # Test bullet point topics
        response = "• artificial intelligence research\n• deep learning applications"
        topics = analyzer._parse_topics_from_response(response)
        assert len(topics) >= 1
    
    def test_extract_sentiment_from_response(self):
        """Test sentiment extraction from response"""
        analyzer = ContentAnalyzer()
        
        # Test positive sentiment
        response = "This is a very positive and optimistic discussion"
        sentiment = analyzer._extract_sentiment_from_response(response)
        assert sentiment == "positive"
        
        # Test negative sentiment
        response = "This is a negative and frustrated conversation"
        sentiment = analyzer._extract_sentiment_from_response(response)
        assert sentiment == "negative"
        
        # Test neutral sentiment
        response = "This is a factual and informational text"
        sentiment = analyzer._extract_sentiment_from_response(response)
        assert sentiment == "neutral"
    
    def test_calculate_confidence(self):
        """Test confidence calculation"""
        analyzer = ContentAnalyzer()
        
        # Test with minimal content and results
        content = "Short"
        results = {"category": "General", "tags": [], "summary": ""}
        confidence = analyzer._calculate_confidence(content, results)
        assert confidence == 0.5  # Base confidence
        
        # Test with good content and results
        content = "This is a longer piece of content with substantial information and details that should increase confidence"
        results = {
            "category": "Technology",
            "tags": ["ai", "tech"],
            "summary": "Good summary",
            "title": "Good title"
        }
        confidence = analyzer._calculate_confidence(content, results)
        assert confidence > 0.7
    
    def test_generate_simple_title(self):
        """Test simple title generation"""
        analyzer = ContentAnalyzer()
        
        # Test with sentence
        content = "This is a test sentence. Another sentence follows."
        title = analyzer._generate_simple_title(content)
        assert title == "This is a test sentence"
        
        # Test with long content
        long_content = "This is a very long sentence that should be truncated because it exceeds the character limit"
        title = analyzer._generate_simple_title(long_content)
        assert len(title) <= 50
        assert title.endswith("...")
        
        # Test with empty content
        title = analyzer._generate_simple_title("")
        assert title == "STT Recording"