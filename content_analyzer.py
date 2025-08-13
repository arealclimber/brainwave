import logging
from typing import Dict, List, Optional, Tuple
from llm_processor import get_llm_processor
from prompts import CONTENT_ANALYSIS_PROMPTS

logger = logging.getLogger(__name__)

class ContentAnalyzer:
    """Analyzes STT content using Gemini for categorization and summarization"""
    
    def __init__(self, model: str = "gemini-2.5-flash"):
        self.model = model
        try:
            self.llm_processor = get_llm_processor("gemini")
            self.enabled = True
            logger.info("Content analyzer initialized with Gemini")
        except Exception as e:
            logger.error(f"Failed to initialize content analyzer: {e}")
            self.llm_processor = None
            self.enabled = False
    
    async def analyze_content(self, content: str) -> Dict:
        """Perform streamlined content analysis for brainstorm ideas"""
        if not self.enabled:
            logger.warning("Content analyzer not enabled, returning basic analysis")
            return self._get_fallback_analysis(content)
        
        try:
            # Run core analysis tasks - only title, summary, and category for speed
            results = await self._run_core_analysis(content)
            
            return {
                "title": results.get("title", self._generate_simple_title(content)),
                "summary": results.get("summary", ""),
                "category": results.get("category", "Top of funnel"),
                "confidence": results.get("confidence", 0.7)
            }
            
        except Exception as e:
            logger.error(f"Error during content analysis: {e}")
            return self._get_fallback_analysis(content)
    
    async def _run_core_analysis(self, content: str) -> Dict:
        """Run core analysis tasks for speed - title, summary, category only"""
        import asyncio
        
        # Create core analysis tasks
        tasks = {
            "title": self._generate_title(content),
            "summary": self._generate_summary(content),
            "category": self._categorize_content(content)
        }
        
        # Run tasks concurrently
        results = {}
        for name, task in tasks.items():
            try:
                results[name] = await task
            except Exception as e:
                logger.error(f"Error in {name} analysis: {e}")
                results[name] = self._get_fallback_value(name)
        
        # Calculate confidence based on content length and successful analysis
        results["confidence"] = self._calculate_simple_confidence(content, results)
        
        return results
    
    async def _generate_title(self, content: str) -> str:
        """Generate a concise title from content"""
        prompt = CONTENT_ANALYSIS_PROMPTS["title_generation"]
        
        try:
            response = ""
            async for chunk in self.llm_processor.process_text(
                content[:1000], prompt, model=self.model
            ):
                response += chunk
            
            # Extract just the title, removing any extra formatting
            title = response.strip().strip('"').strip("'")
            return title[:100] if title else self._generate_simple_title(content)
            
        except Exception as e:
            logger.error(f"Error generating title: {e}")
            return self._generate_simple_title(content)
    
    async def _generate_summary(self, content: str) -> str:
        """Generate an executive summary"""
        prompt = CONTENT_ANALYSIS_PROMPTS["summary_generation"]
        
        try:
            response = ""
            async for chunk in self.llm_processor.process_text(
                content, prompt, model=self.model
            ):
                response += chunk
            
            return response.strip()[:500]  # Limit summary length
            
        except Exception as e:
            logger.error(f"Error generating summary: {e}")
            return ""
    
    async def _categorize_content(self, content: str) -> str:
        """Categorize content into primary category"""
        prompt = CONTENT_ANALYSIS_PROMPTS["categorization"]
        
        try:
            response = ""
            async for chunk in self.llm_processor.process_text(
                content[:1500], prompt, model=self.model
            ):
                response += chunk
            
            # Extract category from response
            category = self._extract_category_from_response(response)
            return category
            
        except Exception as e:
            logger.error(f"Error categorizing content: {e}")
            return "General"
    
    async def _extract_tags(self, content: str) -> List[str]:
        """Extract relevant tags from content"""
        prompt = CONTENT_ANALYSIS_PROMPTS["tag_extraction"]
        
        try:
            response = ""
            async for chunk in self.llm_processor.process_text(
                content[:1500], prompt, model=self.model
            ):
                response += chunk
            
            # Extract tags from response
            tags = self._parse_tags_from_response(response)
            return tags[:8]  # Limit to 8 tags
            
        except Exception as e:
            logger.error(f"Error extracting tags: {e}")
            return []
    
    async def _extract_key_topics(self, content: str) -> List[str]:
        """Extract key topics and themes"""
        prompt = CONTENT_ANALYSIS_PROMPTS["topic_extraction"]
        
        try:
            response = ""
            async for chunk in self.llm_processor.process_text(
                content[:1500], prompt, model=self.model
            ):
                response += chunk
            
            # Extract topics from response
            topics = self._parse_topics_from_response(response)
            return topics[:5]  # Limit to 5 topics
            
        except Exception as e:
            logger.error(f"Error extracting topics: {e}")
            return []
    
    async def _analyze_sentiment(self, content: str) -> str:
        """Analyze overall sentiment of content"""
        prompt = CONTENT_ANALYSIS_PROMPTS["sentiment_analysis"]
        
        try:
            response = ""
            async for chunk in self.llm_processor.process_text(
                content[:1000], prompt, model=self.model
            ):
                response += chunk
            
            # Extract sentiment from response
            sentiment = self._extract_sentiment_from_response(response)
            return sentiment
            
        except Exception as e:
            logger.error(f"Error analyzing sentiment: {e}")
            return "neutral"
    
    def _extract_category_from_response(self, response: str) -> str:
        """Extract category from Gemini response - allow any category name"""
        import re
        
        # Clean up the response to extract the category name
        response = response.strip()
        
        # Remove common prefixes and suffixes
        response = re.sub(r'^(Category:|The category is|This falls under)', '', response, flags=re.IGNORECASE)
        response = re.sub(r'\.$', '', response)
        response = response.strip()
        
        # If response contains multiple lines, take the first meaningful line
        lines = [line.strip() for line in response.split('\n') if line.strip()]
        if lines:
            category = lines[0]
            
            # Handle bullet points or numbered lists
            category = re.sub(r'^[-•\d\.]\s*', '', category)
            category = category.strip()
            
            # Limit length and clean up
            if category and len(category) <= 50:  # Reasonable category name length
                return category.title()
        
        # Fallback if parsing fails
        return "General"
    
    def _parse_tags_from_response(self, response: str) -> List[str]:
        """Parse tags from Gemini response"""
        # Look for comma-separated tags or bullet points
        import re
        
        # Try to find comma-separated tags
        if ',' in response:
            tags = [tag.strip() for tag in response.split(',')]
        else:
            # Try to find bullet points or numbered lists
            tags = re.findall(r'[-•\d\.]\s*([^\n]+)', response)
        
        # Clean up tags
        clean_tags = []
        for tag in tags:
            clean_tag = re.sub(r'[^\w\s]', '', tag).strip()
            if clean_tag and len(clean_tag) > 2:
                clean_tags.append(clean_tag[:20])  # Limit tag length
        
        return clean_tags
    
    def _parse_topics_from_response(self, response: str) -> List[str]:
        """Parse topics from Gemini response"""
        # Similar to tags but potentially longer phrases
        import re
        
        if ',' in response:
            topics = [topic.strip() for topic in response.split(',')]
        else:
            topics = re.findall(r'[-•\d\.]\s*([^\n]+)', response)
        
        clean_topics = []
        for topic in topics:
            clean_topic = topic.strip().strip('.-•')
            if clean_topic and len(clean_topic) > 3:
                clean_topics.append(clean_topic[:50])
        
        return clean_topics
    
    def _extract_sentiment_from_response(self, response: str) -> str:
        """Extract sentiment from Gemini response"""
        response_lower = response.lower()
        
        if any(word in response_lower for word in ['positive', 'happy', 'excited', 'optimistic']):
            return "positive"
        elif any(word in response_lower for word in ['negative', 'sad', 'angry', 'frustrated']):
            return "negative"
        else:
            return "neutral"
    
    def _calculate_confidence(self, content: str, results: Dict) -> float:
        """Calculate confidence score based on content quality and analysis results"""
        confidence = 0.5  # Base confidence
        
        # Content length factor
        if len(content) > 100:
            confidence += 0.2
        if len(content) > 500:
            confidence += 0.1
        
        # Analysis quality factors
        if results.get("category") != "General":
            confidence += 0.1
        if results.get("tags"):
            confidence += 0.1
        if results.get("summary"):
            confidence += 0.1
        
        return min(confidence, 1.0)
    
    def _calculate_simple_confidence(self, content: str, results: Dict) -> float:
        """Calculate simplified confidence score for core analysis"""
        confidence = 0.6  # Base confidence
        
        # Content length factor
        if len(content) > 50:
            confidence += 0.1
        if len(content) > 200:
            confidence += 0.2
        
        # Analysis success factors
        if results.get("title") and len(results["title"]) > 5:
            confidence += 0.1
        if results.get("summary") and len(results["summary"]) > 10:
            confidence += 0.1
        if results.get("category") and results["category"] != "General":
            confidence += 0.1
        
        return min(confidence, 1.0)
    
    def _get_fallback_analysis(self, content: str) -> Dict:
        """Provide basic analysis when Gemini is unavailable"""
        return {
            "title": self._generate_simple_title(content),
            "summary": content[:200] + "..." if len(content) > 200 else content,
            "category": "General",
            "confidence": 0.4
        }
    
    def _generate_simple_title(self, content: str) -> str:
        """Generate a simple title without AI"""
        # Take first sentence or first 50 characters
        sentences = content.split('.')
        if sentences and len(sentences[0].strip()) > 0:
            title = sentences[0].strip()
            if len(title) > 50:
                title = title[:47] + "..."
            return title
        
        return content[:50] + "..." if len(content) > 50 else content or "STT Recording"
    
    def _get_fallback_value(self, analysis_type: str):
        """Get fallback value for failed analysis"""
        fallbacks = {
            "title": "STT Recording",
            "summary": "",
            "category": "General"
        }
        return fallbacks.get(analysis_type, "")

# Global instance
content_analyzer = ContentAnalyzer()
