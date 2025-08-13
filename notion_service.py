import os
import logging
from typing import Dict, Optional, List
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

# Global instance
notion_service = NotionService()