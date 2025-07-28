from typing import Any
import httpx
import os
from datetime import datetime
from enum import Enum
import json
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

# Load environment variables
load_dotenv()

# Initialize FastMCP server
mcp = FastMCP("qloo")

# Constants
QLOO_API_BASE = "https://hackathon.api.qloo.com/v2/insights/"
USER_AGENT = "qloo-app/1.0"

class SocialContext(Enum):
    """Social contexts for cultural analysis"""
    SOLO = "solo"
    COUPLE = "couple"
    FAMILY = "family"
    FRIENDS = "friends"
    BUSINESS = "business"
    LARGE_GROUP = "large_group"
    TOURISTS = "tourists"
    LOCALS = "locals"

async def make_qloo_request(url: str) -> dict[str, Any] | None:
    """Make a request to the QLOO API with proper error handling."""
    qloo_api_key = os.getenv("QLOO_API_KEY")
    if not qloo_api_key:
        return {"error": "QLOO_API_KEY environment variable not set"}
    
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
        "X-Api-Key": qloo_api_key
    }
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers, timeout=30.0)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {"error": f"API request failed: {str(e)}"}

@mcp.tool()
async def analyze_cultural_moment(self, location: str, 
                                social_context: str = "friends", 
                                include_details: bool = True) -> str:
    """Analyze the cultural context and moment for a specific location and social situation.

    Args:
        location: City name (e.g. Mumbai, New York, Tokyo)
        social_context: Social situation (solo, couple, family, friends, business, large_group, tourists, locals)
        include_details: Whether to include detailed cultural breakdown

    
    Returns:
        CulturalMoment: Comprehensive cultural analysis
    """
    if time is None:
        time = datetime.now()
        
    print(f"🔍 Analyzing cultural moment: {location} at {time.strftime('%Y-%m-%d %H:%M')} for {social_context.value}")
        
        # Generate cache key for this specific analysis
    cache_key = f"{location}_{time.date()}_{social_context.value}"
        
    if self.cache_enabled and cache_key in self.cache:
        print("📋 Using cached cultural analysis")
        return self.cache[cache_key]
        
        # Fetch cultural heatmap data
    heatmap = await self._fetch_cultural_heatmap(location)
        
        # Analyze local preferences
    local_preferences = await self._analyze_local_preferences(location, social_context)
        
        # Get demographic insights
    demographics = await self._fetch_demographics(location)
        
        # Generate cultural tags
    cultural_tags = self._generate_cultural_tags(heatmap, local_preferences, demographics)
        
        # Calculate derived metrics
    cultural_intensity = self._calculate_cultural_intensity(heatmap, local_preferences)
    diversity_index = self._calculate_diversity_index(cultural_tags, demographics)
    accessibility_score = self._calculate_accessibility_score(location, social_context)
        
        # Calculate confidence based on data quality
    confidence_score = self._calculate_confidence_score(heatmap, local_preferences, demographics)
        
        # Create the cultural moment
    moment = CulturalMoment(
        location=location,
        timestamp=time,
        social_context=social_context,
        heatmap=heatmap,
        local_preferences=local_preferences,
        demographics=demographics,
        cultural_tags=cultural_tags,
        cultural_intensity=cultural_intensity,
        diversity_index=diversity_index,
        accessibility_score=accessibility_score,
        confidence_score=confidence_score,
        data_sources=["qloo_api", "cultural_analysis", "demographic_inference"]
    )
        
        # Cache the result
    if self.cache_enabled:
        self.cache[cache_key] = moment
        
    print(f"✅ Cultural analysis complete: {moment.get_cultural_summary()}")
    return moment

def format_place_recommendation(item: dict) -> str:
    """Format a place recommendation into a readable string."""
    name = item.get('name', 'Unknown Place')
    
    # Get properties which contains the main details
    properties = item.get('properties', {})
    address = properties.get('address', 'Address not available')
    description = properties.get('description', '')
    rating = properties.get('business_rating', 'No rating')
    phone = properties.get('phone', 'No phone')
    website = properties.get('website', 'No website')
    is_closed = properties.get('is_closed', False)
    
    # Get some popular keywords if available
    keywords = properties.get('keywords', [])
    top_keywords = [kw.get('name', '') for kw in keywords[:3] if kw.get('name')]
    
    # Build the result
    result = f"📍 **{name}**"
    
    if description:
        result += f"\n   {description}"
    
    result += f"\n   📧 Address: {address}"
    
    if rating != 'No rating':
        result += f"\n   ⭐ Rating: {rating}/5"
    
    if phone != 'No phone':
        result += f"\n   📞 Phone: {phone}"
    
    if website != 'No website':
        result += f"\n   🌐 Website: {website}"
    
    if top_keywords:
        result += f"\n   🏷️ Popular for: {', '.join(top_keywords)}"
    
    status = "❌ Closed" if is_closed else "✅ Open"
    result += f"\n   {status}"
    
    return result

@mcp.tool()
async def get_cultural_preferences(location: str, social_context: str = "friends") -> str:
    """Get cultural preferences and local insights for a location and social context."""

@mcp.tool()
async def get_restaurant_recommendations(location: str, cuisine: str = "japanese") -> str:
    """Get restaurant recommendations for a specific cuisine in a location.

    Args:
        location: City name (e.g. Mumbai, New York, Tokyo)
        cuisine: Type of cuisine (default: japanese, options: japanese, italian, chinese, indian, mexican)
    """
    # Build the URL with parameters
    params = {
        "filter.type": "urn:entity:place",
        "filter.tags": f"urn:tag:genre:place:restaurant:{cuisine.lower()}",
        "filter.address": location
    }
    
    # Convert params to query string
    query_params = "&".join([f"{k}={v}" for k, v in params.items()])
    url = f"{QLOO_API_BASE}?{query_params}"
    
    data = await make_qloo_request(url)
    
    if not data:
        return f"Unable to fetch {cuisine} restaurant recommendations for {location}."
    
    if "error" in data:
        return f"Error: {data['error']}"
    
    # Extract results from the response
    results = data.get('results', [])
    if not results:
        return f"No {cuisine} restaurants found in {location}."
    
    # Format the recommendations (limit to top 5)
    recommendations = []
    max_results = min(5, len(results))
    for i in range(max_results):
        recommendations.append(format_place_recommendation(results[i]))
    
    return f"Top {cuisine} restaurants in {location}:\n" + "\n---\n".join(recommendations)

@mcp.tool() 
async def get_place_recommendations(location: str, place_type: str = "restaurant") -> str:
    """Get general place recommendations in a location.

    Args:
        location: City name (e.g. Mumbai, New York, Tokyo)
        place_type: Type of place (default: restaurant, options: restaurant, bar, cafe, shopping, entertainment)
    """
    # Build the URL with parameters
    params = {
        "filter.type": "urn:entity:place",
        "filter.tags": f"urn:tag:genre:place:{place_type.lower()}",
        "filter.address": location
    }
    
    # Convert params to query string
    query_params = "&".join([f"{k}={v}" for k, v in params.items()])
    url = f"{QLOO_API_BASE}?{query_params}"
    
    data = await make_qloo_request(url)
    
    if not data:
        return f"Unable to fetch {place_type} recommendations for {location}."
    
    if "error" in data:
        return f"Error: {data['error']}"
    
    try:
        # Extract results from the response - API returns data in results.entities
        results_data = data.get('results', {})
        results = results_data.get('entities', [])
        
        if not results:
            return f"No {place_type}s found in {location}."
        
        # Format the recommendations (limit to top 5)
        recommendations = []
        max_results = min(5, len(results))
        for i in range(max_results):
            recommendations.append(format_place_recommendation(results[i]))
        
        header = f"🎯 **Top {max_results} {place_type}s in {location}:**\n"
        return header + "\n" + "\n".join([f"{i+1}. {rec}" for i, rec in enumerate(recommendations)])
    
    except Exception as e:
        return f"Error processing results: {str(e)}. Raw API response: {str(data)[:200]}..."