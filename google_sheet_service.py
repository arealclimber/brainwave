"""
Google Sheets integration service for automatic transcript logging.
Inserts transcripts with UTC+8 timestamps into a designated Google Sheet.
"""

import os
import json
import base64
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

import gspread
from google.oauth2.service_account import Credentials

logger = logging.getLogger(__name__)

# UTC+8 timezone
UTC_PLUS_8 = timezone(timedelta(hours=8))

# Google Sheets API scopes
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
]


class GoogleSheetService:
    """Service for inserting transcripts into Google Sheets."""
    
    def __init__(self):
        self.client: Optional[gspread.Client] = None
        self.sheet_id = os.getenv("GOOGLE_SHEET_ID")
        self.sheet_name = "TODO"  # Target sheet/tab name
        self.enabled = False
        
        self._initialize()
    
    def _initialize(self):
        """Initialize the Google Sheets client."""
        if not self.sheet_id:
            logger.warning("GOOGLE_SHEET_ID not set. Google Sheets integration disabled.")
            return
        
        # Get service account credentials
        service_account_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
        
        if not service_account_json:
            logger.warning("GOOGLE_SERVICE_ACCOUNT_JSON not set. Google Sheets integration disabled.")
            return
        
        try:
            # Try to parse as JSON first (plain JSON string)
            try:
                creds_dict = json.loads(service_account_json)
                logger.info("Parsed GOOGLE_SERVICE_ACCOUNT_JSON as plain JSON")
            except json.JSONDecodeError as json_err:
                logger.info(f"Not plain JSON, trying Base64 decode: {json_err}")
                # Try to decode as base64
                try:
                    # Remove any whitespace/newlines that might be in base64 string
                    clean_b64 = service_account_json.strip().replace('\n', '').replace('\r', '')
                    # Add padding if needed
                    padding = 4 - len(clean_b64) % 4
                    if padding != 4:
                        clean_b64 += '=' * padding
                    decoded = base64.b64decode(clean_b64).decode('utf-8')
                    creds_dict = json.loads(decoded)
                    logger.info("Parsed GOOGLE_SERVICE_ACCOUNT_JSON as Base64")
                except Exception as e:
                    logger.error(f"Failed to parse GOOGLE_SERVICE_ACCOUNT_JSON as Base64: {e}")
                    logger.error(f"JSON content preview: {service_account_json[:100]}...")
                    return
            
            # Create credentials
            credentials = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
            
            # Initialize gspread client
            self.client = gspread.authorize(credentials)
            self.enabled = True
            logger.info(f"Google Sheets integration enabled. Sheet ID: {self.sheet_id}")
            
        except Exception as e:
            logger.error(f"Failed to initialize Google Sheets client: {e}")
            self.enabled = False
    
    def _get_utc8_timestamp(self) -> str:
        """Get current timestamp in UTC+8 as 'MM/DD HH:MM' format for Google Sheet."""
        now = datetime.now(UTC_PLUS_8)
        return now.strftime("%m/%d %H:%M")
    
    async def insert_transcript(self, content: str, category: Optional[str] = None) -> dict:
        """
        Insert a transcript row into the Google Sheet.
        
        Args:
            content: The transcript content to insert
            category: Optional category (e.g., 'todo')
            
        Returns:
            dict with success status and message
        """
        if not self.enabled:
            return {
                "success": False,
                "error": "Google Sheets integration is not enabled"
            }
        
        if not content or not content.strip():
            return {
                "success": False,
                "error": "Content is empty"
            }
        
        try:
            # Open the spreadsheet
            spreadsheet = self.client.open_by_key(self.sheet_id)
            
            # Get or create the TODO sheet
            try:
                worksheet = spreadsheet.worksheet(self.sheet_name)
            except gspread.WorksheetNotFound:
                # Create the sheet if it doesn't exist
                worksheet = spreadsheet.add_worksheet(title=self.sheet_name, rows=1000, cols=10)
                logger.info(f"Created new worksheet: {self.sheet_name}")
            
            # Get timestamp
            timestamp = self._get_utc8_timestamp()
            
            # Insert row at the top (after header if exists, or at row 2)
            # This puts newest entries at the top
            # Row format: Date | Content | Category (if provided)
            row_data = [timestamp, content.strip(), category or ""]
            worksheet.insert_row(row_data, index=2)
            
            logger.info(f"Inserted transcript to Google Sheet: {timestamp} - {content[:50]}... (category: {category})")
            
            return {
                "success": True,
                "message": "Successfully saved to Google Sheet",
                "timestamp": timestamp
            }
            
        except gspread.exceptions.SpreadsheetNotFound:
            error_msg = f"Spreadsheet not found: {self.sheet_id}"
            logger.error(error_msg)
            return {"success": False, "error": error_msg}
            
        except gspread.exceptions.APIError as e:
            error_msg = f"Google Sheets API error: {e}"
            logger.error(error_msg)
            return {"success": False, "error": error_msg}
            
        except Exception as e:
            error_msg = f"Failed to insert transcript: {e}"
            logger.error(error_msg, exc_info=True)
            return {"success": False, "error": error_msg}
    
    async def check_connection(self) -> bool:
        """Check if the Google Sheets connection is working."""
        if not self.enabled:
            return False
        
        try:
            spreadsheet = self.client.open_by_key(self.sheet_id)
            # Try to access the sheet
            spreadsheet.worksheet(self.sheet_name)
            return True
        except Exception as e:
            logger.error(f"Google Sheets connection check failed: {e}")
            return False


# Singleton instance
google_sheet_service = GoogleSheetService()

