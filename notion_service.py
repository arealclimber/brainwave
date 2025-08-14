import os
import logging
import re
from typing import Dict, Optional, List, Any
from datetime import datetime
from notion_client import Client
# Import only what we need from notion_client

logger = logging.getLogger(__name__)

class NotionService:
    """Service for creating and managing Notion pages from STT transcriptions"""
    
    def __init__(self):
        self.token = os.getenv("NOTION_TOKEN")
        self.database_id = os.getenv("NOTION_DATABASE_ID")
        self.client = None
        self.enabled = False
        
        if self.token and self.database_id:
            try:
                self.client = Client(auth=self.token)
                self.enabled = True
                logger.info("Notion service initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize Notion client: {e}")
        else:
            logger.warning("Notion integration disabled: NOTION_TOKEN or NOTION_DATABASE_ID not set")
    
    async def create_stt_note(
        self, 
        content: str, 
        title: str = None,
        summary: str = None,
        category: str = None,
        confidence: float = None
    ) -> Optional[Dict]:
        """Create a new note in Notion from STT transcription"""
        if not self.enabled:
            logger.warning("Notion service not enabled, skipping note creation")
            return None
            
        try:
            # Generate title if not provided
            if not title:
                title = self._generate_title_from_content(content)
            
            # Start with minimal properties and add based on what works
            properties = {}
            
            # Idea is the title field - this should always work
            properties["Idea"] = {
                "title": [
                    {
                        "text": {
                            "content": title[:100] if title else "STT Recording"
                        }
                    }
                ]
            }
            
            # Try adding other properties conditionally
            try:
                # Status field - check logs to see actual format needed
                properties["Status"] = {
                    "status": {
                        "name": "New idea"
                    }
                }
                
                # Priority field  
                properties["Priority"] = {
                    "select": {
                        "name": "Low"
                    }
                }
                
                # Brief field (if summary provided)
                if summary and summary.strip():
                    properties["Brief"] = {
                        "rich_text": [
                            {
                                "text": {
                                    "content": summary[:2000]
                                }
                            }
                        ]
                    }
                
                # Category field as multi_select
                if category and category.strip():
                    clean_category = category.strip().title()
                    properties["Category"] = {
                        "multi_select": [
                            {
                                "name": clean_category
                            }
                        ]
                    }
                else:
                    properties["Category"] = {
                        "multi_select": [
                            {
                                "name": "General"
                            }
                        ]
                    }
            except Exception as prop_error:
                logger.error(f"Error setting properties: {prop_error}")
                # Fall back to just title
                properties = {
                    "Idea": {
                        "title": [
                            {
                                "text": {
                                    "content": title[:100] if title else "STT Recording"
                                }
                            }
                        ]
                    }
                }
            
            # Prepare page content
            children = [
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [
                            {
                                "type": "text",
                                "text": {
                                    "content": content[:2000]  # First chunk
                                }
                            }
                        ]
                    }
                }
            ]
            
            # If content is longer, add additional blocks
            if len(content) > 2000:
                remaining_content = content[2000:]
                while remaining_content:
                    chunk = remaining_content[:2000]
                    remaining_content = remaining_content[2000:]
                    children.append({
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {
                            "rich_text": [
                                {
                                    "type": "text",
                                    "text": {
                                        "content": chunk
                                    }
                                }
                            ]
                        }
                    })
            
            # Log the request for debugging
            request_data = {
                "parent": {"database_id": self.database_id},
                "properties": properties,
                "children": children
            }
            logger.info(f"Creating page with data: {request_data}")
            
            # Create the page
            response = self.client.pages.create(
                parent={"database_id": self.database_id},
                properties=properties,
                children=children
            )
            
            logger.info(f"Successfully created Notion page: {response['url']}")
            return {
                "page_id": response["id"],
                "url": response["url"],
                "title": title
            }
            
        except Exception as e:
            logger.error(f"Unexpected error creating Notion page: {e}")
            return None
    
    def _generate_title_from_content(self, content: str) -> str:
        """Generate a title from content if none provided"""
        # Simple title generation - take first sentence or first 50 chars
        sentences = content.split('.')
        if sentences and len(sentences[0].strip()) > 0:
            title = sentences[0].strip()
            if len(title) > 50:
                title = title[:47] + "..."
            return title
        
        # Fallback to first 50 characters
        if len(content) > 50:
            return content[:47] + "..."
        return content or "STT Transcription"
    
    async def check_connection(self) -> bool:
        """Check if Notion API connection is working"""
        if not self.enabled:
            return False
            
        try:
            # Try to retrieve database info and log properties for debugging
            db_info = self.client.databases.retrieve(self.database_id)
            logger.info(f"Database properties: {list(db_info.get('properties', {}).keys())}")
            
            # Log each property type for debugging
            for prop_name, prop_info in db_info.get('properties', {}).items():
                prop_type = prop_info.get('type', 'unknown')
                logger.info(f"Property '{prop_name}': type={prop_type}")
            
            return True
        except Exception as e:
            logger.error(f"Notion connection check failed: {e}")
            return False
    
    # Word count tracking methods
    async def get_database_pages(self) -> List[Dict]:
        """Get all pages from the database sorted by last_edited_time"""
        if not self.enabled:
            return []
            
        try:
            response = self.client.databases.query(
                database_id=self.database_id,
                sorts=[
                    {
                        "property": "last_edited_time",
                        "direction": "descending"
                    }
                ]
            )
            
            pages = []
            for page in response["results"]:
                pages.append({
                    "page_id": page["id"],
                    "last_edited_time": page["last_edited_time"],
                    "url": page["url"],
                    "properties": page["properties"]
                })
            
            logger.info(f"Retrieved {len(pages)} pages from database")
            return pages
            
        except Exception as e:
            logger.error(f"Failed to get database pages: {e}")
            return []
    
    async def get_page_content(self, page_id: str) -> str:
        """Get the full content of a page and return as text"""
        if not self.enabled:
            return ""
            
        try:
            # Get page blocks
            response = self.client.blocks.children.list(block_id=page_id)
            content_text = ""
            
            for block in response["results"]:
                text = self._extract_text_from_block(block)
                if text:
                    content_text += text + "\n"
            
            return content_text.strip()
            
        except Exception as e:
            logger.error(f"Failed to get page content for {page_id}: {e}")
            return ""
    
    def _extract_text_from_block(self, block: Dict) -> str:
        """Extract text content from a Notion block"""
        block_type = block.get("type")
        
        if not block_type:
            return ""
        
        # Handle different block types
        text_content = ""
        
        if block_type in ["paragraph", "heading_1", "heading_2", "heading_3", 
                         "bulleted_list_item", "numbered_list_item", "quote", "callout"]:
            rich_text_key = block_type
            if block_type.startswith("heading_"):
                rich_text_key = block_type
            
            rich_texts = block.get(rich_text_key, {}).get("rich_text", [])
            for rich_text in rich_texts:
                if "text" in rich_text:
                    text_content += rich_text["text"]["content"]
        
        elif block_type == "code":
            rich_texts = block.get("code", {}).get("rich_text", [])
            for rich_text in rich_texts:
                if "text" in rich_text:
                    text_content += rich_text["text"]["content"]
        
        elif block_type == "to_do":
            rich_texts = block.get("to_do", {}).get("rich_text", [])
            for rich_text in rich_texts:
                if "text" in rich_text:
                    text_content += rich_text["text"]["content"]
        
        return text_content
    
    def count_words(self, text: str) -> int:
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
        logger.debug(f"Word count: {total_words} (Chinese: {chinese_count}, English: {english_count})")
        
        return total_words
    
    async def update_word_count(self, page_id: str, word_count: int) -> bool:
        """Update the Words field for a specific page"""
        if not self.enabled:
            return False
            
        try:
            self.client.pages.update(
                page_id=page_id,
                properties={
                    "Words": {
                        "number": word_count
                    }
                }
            )
            
            logger.info(f"Updated word count for page {page_id}: {word_count} words")
            return True
            
        except Exception as e:
            logger.error(f"Failed to update word count for page {page_id}: {e}")
            return False
    
    async def calculate_and_update_word_count(self, page_id: str) -> Optional[int]:
        """Calculate word count for a page and update the Words field"""
        try:
            # Get page content
            content = await self.get_page_content(page_id)
            
            # Calculate word count
            word_count = self.count_words(content)
            
            # Update the Words field
            success = await self.update_word_count(page_id, word_count)
            
            if success:
                logger.info(f"Successfully calculated and updated word count for page {page_id}: {word_count} words")
                return word_count
            else:
                logger.error(f"Failed to update word count for page {page_id}")
                return None
                
        except Exception as e:
            logger.error(f"Failed to calculate and update word count for page {page_id}: {e}")
            return None

# Global instance
notion_service = NotionService()