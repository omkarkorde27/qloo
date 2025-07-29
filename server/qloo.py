from typing import Any
import httpx
import os
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

# Load environment variables
load_dotenv()

# Initialize FastMCP server
mcp = FastMCP("qloo")

# Constants
QLOO_API_BASE = "https://hackathon.api.qloo.com/v2/insights/"
USER_AGENT = "qloo-app/1.0"


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