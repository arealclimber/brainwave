import pytest
import os
from unittest.mock import patch, MagicMock, AsyncMock
from notion_service import NotionService

class TestNotionService:
    
    def test_init_without_credentials(self):
        """Test NotionService initialization without credentials"""
        with patch.dict(os.environ, {}, clear=True):
            service = NotionService()
            assert not service.enabled
            assert service.client is None
    
    def test_init_with_credentials(self):
        """Test NotionService initialization with credentials"""
        with patch.dict(os.environ, {
            'NOTION_TOKEN': 'test_token',
            'NOTION_DATABASE_ID': 'test_db_id'
        }):
            with patch('notion_service.Client') as mock_client:
                service = NotionService()
                assert service.enabled
                assert service.token == 'test_token'
                assert service.database_id == 'test_db_id'
                mock_client.assert_called_once_with(auth='test_token')
    
    @pytest.mark.asyncio
    async def test_create_stt_note_disabled(self):
        """Test creating note when service is disabled"""
        with patch.dict(os.environ, {}, clear=True):
            service = NotionService()
            result = await service.create_stt_note("test content")
            assert result is None
    
    @pytest.mark.asyncio
    async def test_create_stt_note_success(self):
        """Test successful note creation"""
        with patch.dict(os.environ, {
            'NOTION_TOKEN': 'test_token',
            'NOTION_DATABASE_ID': 'test_db_id'
        }):
            mock_client = MagicMock()
            mock_response = {
                'id': 'test_page_id',
                'url': 'https://notion.so/test_page_id'
            }
            mock_client.pages.create.return_value = mock_response
            
            with patch('notion_service.Client', return_value=mock_client):
                service = NotionService()
                
                result = await service.create_stt_note(
                    content="Test transcript content",
                    title="Test Title",
                    summary="Test Summary",
                    category="Technology",
                    tags=["test", "transcript"],
                    confidence=0.95
                )
                
                assert result is not None
                assert result['page_id'] == 'test_page_id'
                assert result['url'] == 'https://notion.so/test_page_id'
                assert result['title'] == "Test Title"
                
                # Verify the client was called with correct parameters
                mock_client.pages.create.assert_called_once()
                call_args = mock_client.pages.create.call_args
                assert call_args[1]['parent']['database_id'] == 'test_db_id'
    
    def test_generate_title_from_content(self):
        """Test title generation from content"""
        with patch.dict(os.environ, {}, clear=True):
            service = NotionService()
            
            # Test with sentence
            content = "This is a test sentence. This is another sentence."
            title = service._generate_title_from_content(content)
            assert title == "This is a test sentence"
            
            # Test with long content
            long_content = "This is a very long sentence that exceeds fifty characters and should be truncated."
            title = service._generate_title_from_content(long_content)
            assert len(title) <= 50
            assert title.endswith("...")
            
            # Test with short content
            short_content = "Short"
            title = service._generate_title_from_content(short_content)
            assert title == "Short"
    
    @pytest.mark.asyncio
    async def test_check_connection_disabled(self):
        """Test connection check when service is disabled"""
        with patch.dict(os.environ, {}, clear=True):
            service = NotionService()
            result = await service.check_connection()
            assert result is False
    
    @pytest.mark.asyncio
    async def test_check_connection_success(self):
        """Test successful connection check"""
        with patch.dict(os.environ, {
            'NOTION_TOKEN': 'test_token',
            'NOTION_DATABASE_ID': 'test_db_id'
        }):
            mock_client = MagicMock()
            mock_client.databases.retrieve.return_value = {"id": "test_db_id"}
            
            with patch('notion_service.Client', return_value=mock_client):
                service = NotionService()
                result = await service.check_connection()
                assert result is True
                mock_client.databases.retrieve.assert_called_once_with('test_db_id')
    
    @pytest.mark.asyncio
    async def test_check_connection_error(self):
        """Test connection check with error"""
        with patch.dict(os.environ, {
            'NOTION_TOKEN': 'test_token',
            'NOTION_DATABASE_ID': 'test_db_id'
        }):
            mock_client = MagicMock()
            mock_client.databases.retrieve.side_effect = Exception("Connection error")
            
            with patch('notion_service.Client', return_value=mock_client):
                service = NotionService()
                result = await service.check_connection()
                assert result is False