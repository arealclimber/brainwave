import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, Set
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from notion_service import notion_service
from state_manager import state_manager

logger = logging.getLogger(__name__)

class NotionWordCountMonitor:
    """Monitor for Notion pages and automatic word count updates"""
    
    def __init__(self, check_interval_minutes: int = 1):
        self.scheduler = AsyncIOScheduler()
        self.check_interval_minutes = check_interval_minutes
        self.is_running = False
        self.last_check_time = None
        self.stats = {
            "total_checks": 0,
            "total_updates": 0,
            "last_error": None,
            "pages_processed": 0
        }
        
    async def start(self) -> bool:
        """Start the monitoring service"""
        try:
            if not notion_service.enabled:
                logger.error("Notion service is not enabled, cannot start monitoring")
                return False
            
            # Load existing state
            await state_manager.load_state()
            
            # Test connection
            if not await notion_service.check_connection():
                logger.error("Failed to connect to Notion API, cannot start monitoring")
                return False
            
            # Schedule the monitoring job
            self.scheduler.add_job(
                self._monitor_pages,
                trigger=IntervalTrigger(minutes=self.check_interval_minutes),
                id='notion_word_count_monitor',
                name='Notion Word Count Monitor',
                max_instances=1,
                coalesce=True
            )
            
            # Start the scheduler
            self.scheduler.start()
            self.is_running = True
            
            logger.info(f"Started Notion word count monitor (checking every {self.check_interval_minutes} minutes)")
            
            # Run initial check
            await self._monitor_pages()
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to start monitoring service: {e}")
            return False
    
    async def stop(self) -> None:
        """Stop the monitoring service"""
        try:
            if self.scheduler.running:
                self.scheduler.shutdown(wait=True)
            self.is_running = False
            logger.info("Stopped Notion word count monitor")
        except Exception as e:
            logger.error(f"Error stopping monitoring service: {e}")
    
    async def _monitor_pages(self) -> None:
        """Main monitoring function that checks for page changes"""
        try:
            start_time = datetime.now()
            self.stats["total_checks"] += 1
            
            logger.info("Starting page monitoring check...")
            
            # Get all pages from database
            pages = await notion_service.get_database_pages()
            
            if not pages:
                logger.warning("No pages found in database")
                return
            
            # Check for changes
            changed_pages = state_manager.get_changed_pages(pages)
            
            if not changed_pages:
                logger.info(f"No changes detected in {len(pages)} pages")
                await state_manager.save_state()
                return
            
            logger.info(f"Detected changes in {len(changed_pages)} pages")
            
            # Update word counts for changed pages
            updated_count = 0
            for page_id in changed_pages:
                try:
                    word_count = await notion_service.calculate_and_update_word_count(page_id)
                    if word_count is not None:
                        updated_count += 1
                        self.stats["pages_processed"] += 1
                        logger.info(f"Updated word count for page {page_id}: {word_count} words")
                    else:
                        logger.warning(f"Failed to update word count for page {page_id}")
                        
                except Exception as e:
                    logger.error(f"Error processing page {page_id}: {e}")
                    continue
                
                # Add small delay to avoid hitting rate limits
                await asyncio.sleep(0.5)
            
            # Save updated state
            await state_manager.save_state()
            
            # Update stats
            self.stats["total_updates"] += updated_count
            self.last_check_time = start_time
            
            check_duration = (datetime.now() - start_time).total_seconds()
            logger.info(f"Monitoring check completed: {updated_count}/{len(changed_pages)} pages updated in {check_duration:.2f}s")
            
        except Exception as e:
            logger.error(f"Error in monitoring check: {e}")
            self.stats["last_error"] = str(e)
    
    async def manual_update_page(self, page_id: str) -> Optional[int]:
        """Manually update word count for a specific page"""
        try:
            logger.info(f"Manual update requested for page {page_id}")
            word_count = await notion_service.calculate_and_update_word_count(page_id)
            
            if word_count is not None:
                # Update the page state to current time
                current_time = datetime.now().isoformat()
                state_manager.update_page_state(page_id, current_time)
                await state_manager.save_state()
                
                self.stats["pages_processed"] += 1
                logger.info(f"Manual update completed for page {page_id}: {word_count} words")
                
            return word_count
            
        except Exception as e:
            logger.error(f"Error in manual update for page {page_id}: {e}")
            return None
    
    async def manual_update_all(self) -> dict:
        """Manually update word counts for all pages"""
        try:
            logger.info("Manual update requested for all pages")
            
            pages = await notion_service.get_database_pages()
            if not pages:
                return {"success": False, "message": "No pages found"}
            
            updated_count = 0
            error_count = 0
            
            for page in pages:
                page_id = page["page_id"]
                try:
                    word_count = await notion_service.calculate_and_update_word_count(page_id)
                    if word_count is not None:
                        updated_count += 1
                        # Update state
                        state_manager.update_page_state(page_id, page["last_edited_time"])
                    else:
                        error_count += 1
                except Exception as e:
                    logger.error(f"Error updating page {page_id}: {e}")
                    error_count += 1
                
                # Rate limiting
                await asyncio.sleep(0.5)
            
            # Save updated state
            await state_manager.save_state()
            
            self.stats["pages_processed"] += updated_count
            
            result = {
                "success": True,
                "updated": updated_count,
                "errors": error_count,
                "total": len(pages)
            }
            
            logger.info(f"Manual update all completed: {updated_count}/{len(pages)} pages updated, {error_count} errors")
            return result
            
        except Exception as e:
            logger.error(f"Error in manual update all: {e}")
            return {"success": False, "message": str(e)}
    
    def get_status(self) -> dict:
        """Get current status of the monitoring service"""
        return {
            "running": self.is_running,
            "check_interval_minutes": self.check_interval_minutes,
            "last_check_time": self.last_check_time.isoformat() if self.last_check_time else None,
            "stats": self.stats.copy(),
            "state_manager_stats": state_manager.get_stats(),
            "notion_service_enabled": notion_service.enabled
        }
    
    async def health_check(self) -> dict:
        """Perform health check"""
        try:
            # Check Notion connection
            notion_ok = await notion_service.check_connection()
            
            # Check state manager
            state_stats = state_manager.get_stats()
            
            return {
                "healthy": notion_ok and self.is_running,
                "notion_connection": notion_ok,
                "monitor_running": self.is_running,
                "state_manager": state_stats,
                "last_check": self.last_check_time.isoformat() if self.last_check_time else None
            }
            
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return {
                "healthy": False,
                "error": str(e)
            }

# Global instance
word_count_monitor = NotionWordCountMonitor(check_interval_minutes=1)