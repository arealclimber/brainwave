import os
import logging
import re
import asyncio
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
                self.client = Client(auth=self.token, notion_version="2022-06-28")
                self.enabled = True
                logger.info("Notion service initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize Notion client: {e}")
        else:
            logger.warning("Notion integration disabled: NOTION_TOKEN or NOTION_DATABASE_ID not set")

    def _query_database(self, **kwargs) -> Dict:
        """Query the database (notion-client v3 removed databases.query, use raw request)"""
        body = {k: v for k, v in kwargs.items()
                if k in ("sorts", "filter", "start_cursor", "page_size", "archived")}
        return self.client.request(
            path=f"databases/{self.database_id}/query",
            method="POST",
            body=body,
        )

    async def create_stt_note(
        self, 
        content: str, 
        title: str = None,
        summary: str = None,
        category: str = None,
        confidence: float = None,
        auto_calculate_words: bool = True
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
                        "name": "Raw Capture"
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
                
                # Words field - calculate and add word count if enabled
                if auto_calculate_words:
                    word_count = self.count_words(content)
                    properties["Words"] = {
                        "number": word_count
                    }
                    logger.info(f"Calculated word count for new page: {word_count} words")
            except Exception as prop_error:
                logger.error(f"Error setting properties: {prop_error}")
                # Fall back to just title and word count
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
                
                # Still try to add word count even in fallback
                if auto_calculate_words:
                    try:
                        word_count = self.count_words(content)
                        properties["Words"] = {
                            "number": word_count
                        }
                        logger.info(f"Calculated word count for new page (fallback): {word_count} words")
                    except Exception as word_error:
                        logger.warning(f"Failed to calculate word count in fallback: {word_error}")
            
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
    
    async def get_recent_notes(self, limit: int = 10) -> List[Dict]:
        """Get recent notes from the database with their content"""
        if not self.enabled:
            return []

        try:
            response = self._query_database(
                page_size=limit,
                sorts=[
                    {
                        "property": "Last edited time",
                        "direction": "descending"
                    }
                ]
            )

            pages = response.get("results", [])
            if not pages:
                return []

            notes = []
            for page in pages:
                page_id = page["id"]
                # Extract title from Idea property
                title = "Untitled"
                idea_prop = page.get("properties", {}).get("Idea", {})
                title_items = idea_prop.get("title", [])
                if title_items:
                    title = "".join(
                        t.get("text", {}).get("content", "") for t in title_items
                    )

                content = await self.get_page_content(page_id)

                # Get last_edited_time
                last_edited = None
                custom_prop = page.get("properties", {}).get("Last edited time", {})
                if custom_prop.get("type") == "last_edited_time":
                    last_edited = custom_prop.get("last_edited_time")
                if not last_edited:
                    last_edited = page.get("last_edited_time")

                notes.append({
                    "page_id": page_id,
                    "title": title,
                    "content": content,
                    "url": page.get("url", ""),
                    "last_edited_time": last_edited,
                })

            logger.info(f"Retrieved {len(notes)} recent notes")
            return notes

        except Exception as e:
            logger.error(f"Failed to get recent notes: {e}")
            return []

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
            response = self._query_database(
                sorts=[
                    {
                        "property": "Last edited time",
                        "direction": "descending"
                    }
                ]
            )

            pages = []
            for page in response["results"]:
                # Try to get custom "Last edited time" property first, fallback to system property
                custom_last_edited = None
                if "Last edited time" in page.get("properties", {}):
                    custom_prop = page["properties"]["Last edited time"]
                    if custom_prop.get("type") == "last_edited_time":
                        custom_last_edited = custom_prop.get("last_edited_time")
                
                # Use custom property if available, otherwise use system property
                last_edited_time = custom_last_edited or page["last_edited_time"]
                
                pages.append({
                    "page_id": page["id"],
                    "last_edited_time": last_edited_time,
                    "url": page["url"],
                    "properties": page["properties"]
                })
            
            logger.info(f"Retrieved {len(pages)} pages from database")
            return pages
            
        except Exception as e:
            logger.error(f"Failed to get database pages: {e}")
            return []
    
    # H1 headings that mark AI-generated sections (not part of original transcript)
    AI_SECTION_HEADINGS = {"readability", "correctness", "ask ai"}

    async def get_page_content(self, page_id: str) -> str:
        """Get the transcript content of a page, stopping before AI-generated sections
        (Readability, Correctness, Ask AI headings and everything after them)"""
        if not self.enabled:
            return ""

        try:
            # Get page blocks
            response = self.client.blocks.children.list(block_id=page_id)
            content_text = ""

            for block in response["results"]:
                # Stop at AI-generated section headings
                if block.get("type") == "heading_1":
                    heading_texts = block.get("heading_1", {}).get("rich_text", [])
                    heading_str = "".join(
                        rt.get("text", {}).get("content", "") for rt in heading_texts
                    ).strip().lower()
                    if heading_str in self.AI_SECTION_HEADINGS:
                        logger.debug(f"Stopping content read at '{heading_str}' section")
                        break

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
    
    async def append_to_page(self, page_id: str, section_title: str, content: str) -> bool:
        """Append content with H1 section title to an existing page"""
        if not self.enabled:
            logger.warning("Notion service not enabled, skipping append")
            return False
            
        try:
            # Create blocks to append: H1 title + content paragraphs
            blocks_to_append = [
                {
                    "object": "block",
                    "type": "heading_1",
                    "heading_1": {
                        "rich_text": [
                            {
                                "type": "text",
                                "text": {
                                    "content": section_title
                                }
                            }
                        ]
                    }
                }
            ]
            
            # Add content as paragraphs (split by 2000 chars limit)
            remaining_content = content
            while remaining_content:
                chunk = remaining_content[:2000]
                remaining_content = remaining_content[2000:]
                blocks_to_append.append({
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
            
            # Append blocks to the page
            self.client.blocks.children.append(
                block_id=page_id,
                children=blocks_to_append
            )
            
            logger.info(f"Successfully appended '{section_title}' to page {page_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to append to page {page_id}: {e}")
            return False

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

    async def update_title_and_summary(self, page_id: str, title: str = None,
                                       summary: str = None, category: str = None) -> bool:
        """Update the title (Idea), summary (Brief), and category for a specific page"""
        if not self.enabled:
            return False

        try:
            properties = {}

            if title:
                properties["Idea"] = {
                    "title": [
                        {
                            "text": {
                                "content": title[:100]
                            }
                        }
                    ]
                }

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

            if category and category.strip():
                properties["Category"] = {
                    "multi_select": [
                        {
                            "name": category.strip().title()
                        }
                    ]
                }

            if not properties:
                logger.warning(f"No properties to update for page {page_id}")
                return False

            self.client.pages.update(
                page_id=page_id,
                properties=properties
            )

            logger.info(f"Updated title/summary for page {page_id}: title={title[:50] if title else 'N/A'}")
            return True

        except Exception as e:
            logger.error(f"Failed to update title/summary for page {page_id}: {e}")
            return False

    async def update_checkbox(self, page_id: str, property_name: str, checked: bool = True) -> bool:
        """Update a checkbox property for a specific page"""
        if not self.enabled:
            return False
            
        try:
            self.client.pages.update(
                page_id=page_id,
                properties={
                    property_name: {
                        "checkbox": checked
                    }
                }
            )
            
            logger.info(f"Updated checkbox '{property_name}' for page {page_id}: {checked}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to update checkbox '{property_name}' for page {page_id}: {e}")
            return False

# Global instance
notion_service = NotionService()
