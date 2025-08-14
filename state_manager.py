import os
import json
import logging
import aiofiles
from typing import Dict, Set, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

class StateManager:
    """Manages page state to detect changes in Notion database"""
    
    def __init__(self, state_file_path: str = "notion_state.json"):
        self.state_file_path = state_file_path
        self.page_states = {}
        
    async def load_state(self) -> Dict[str, str]:
        """Load page states from file"""
        try:
            if os.path.exists(self.state_file_path):
                async with aiofiles.open(self.state_file_path, 'r') as f:
                    content = await f.read()
                    self.page_states = json.loads(content)
                    logger.info(f"Loaded state for {len(self.page_states)} pages")
            else:
                logger.info("No existing state file found, starting fresh")
                self.page_states = {}
        except Exception as e:
            logger.error(f"Failed to load state: {e}")
            self.page_states = {}
        
        return self.page_states
    
    async def save_state(self) -> bool:
        """Save current page states to file"""
        try:
            async with aiofiles.open(self.state_file_path, 'w') as f:
                await f.write(json.dumps(self.page_states, indent=2))
            logger.info(f"Saved state for {len(self.page_states)} pages")
            return True
        except Exception as e:
            logger.error(f"Failed to save state: {e}")
            return False
    
    def get_page_last_edited_time(self, page_id: str) -> Optional[str]:
        """Get the last recorded edit time for a page"""
        return self.page_states.get(page_id)
    
    def update_page_state(self, page_id: str, last_edited_time: str) -> None:
        """Update the last edited time for a page"""
        self.page_states[page_id] = last_edited_time
        logger.debug(f"Updated state for page {page_id}: {last_edited_time}")
    
    def has_page_changed(self, page_id: str, current_last_edited_time: str) -> bool:
        """Check if a page has changed since last check"""
        stored_time = self.get_page_last_edited_time(page_id)
        
        if stored_time is None:
            # First time seeing this page, consider it changed
            logger.info(f"New page detected: {page_id}")
            return True
        
        # Compare timestamps
        changed = stored_time != current_last_edited_time
        if changed:
            logger.info(f"Page {page_id} changed: {stored_time} -> {current_last_edited_time}")
        
        return changed
    
    def get_changed_pages(self, current_pages: list) -> Set[str]:
        """Get list of pages that have changed"""
        changed_pages = set()
        
        for page in current_pages:
            page_id = page["page_id"]
            current_time = page["last_edited_time"]
            
            if self.has_page_changed(page_id, current_time):
                changed_pages.add(page_id)
                # Update state immediately after detecting change
                self.update_page_state(page_id, current_time)
        
        return changed_pages
    
    async def update_and_save_states(self, pages: list) -> bool:
        """Update states for all pages and save to file"""
        try:
            for page in pages:
                page_id = page["page_id"]
                last_edited_time = page["last_edited_time"]
                self.update_page_state(page_id, last_edited_time)
            
            return await self.save_state()
        except Exception as e:
            logger.error(f"Failed to update and save states: {e}")
            return False
    
    def remove_page(self, page_id: str) -> None:
        """Remove a page from tracking (useful if page is deleted)"""
        if page_id in self.page_states:
            del self.page_states[page_id]
            logger.info(f"Removed page {page_id} from tracking")
    
    def get_stats(self) -> Dict:
        """Get statistics about tracked pages"""
        return {
            "total_pages": len(self.page_states),
            "state_file": self.state_file_path,
            "state_file_exists": os.path.exists(self.state_file_path)
        }

# Global instance
state_manager = StateManager()