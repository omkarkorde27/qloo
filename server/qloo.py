from typing import Any, Dict, List
import httpx
import os
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

# Load environment variables
load_dotenv()

# Initialize FastMCP server
mcp = FastMCP("cultureshift_ai")

# Constants
QLOO_API_BASE = "https://hackathon.api.qloo.com/v2/insights/"
USER_AGENT = "cultureshift-ai/1.0"

async def make_qloo_request(url: str) -> Dict[str, Any]:
    """Make a request to the QLOO API with proper error handling and URL encoding."""
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
            # Debug: print the URL being called
            print(f"DEBUG: Calling URL: {url}")
            
            response = await client.get(url, headers=headers, timeout=30.0)
            
            # Debug: print response status
            print(f"DEBUG: Response status: {response.status_code}")
            
            if response.status_code == 400:
                response_text = response.text
                print(f"DEBUG: 400 Error response: {response_text}")
                return {"error": f"Bad Request - Invalid parameters. Response: {response_text[:200]}..."}
            
            response.raise_for_status()
            return response.json()
            
        except Exception as e:
            print(f"DEBUG: Exception occurred: {str(e)}")
            return {"error": f"API request failed: {str(e)}"}

def format_cultural_hotspot(hotspot: Dict) -> str:
    """Format a cultural hotspot data point into readable string."""
    location = hotspot.get('location', {})
    query_data = hotspot.get('query', {})
    
    lat = location.get('latitude', 'Unknown')
    lng = location.get('longitude', 'Unknown')
    geohash = location.get('geohash', 'Unknown')
    
    affinity = query_data.get('affinity', 0)
    affinity_rank = query_data.get('affinity_rank', 0)
    popularity = query_data.get('popularity', 0)
    
    return f"""
🎯 **Cultural Hotspot** ({geohash})
   📍 Location: {lat}, {lng}
   🔥 Cultural Affinity: {affinity:.3f}
   📊 Affinity Rank: {affinity_rank:.3f}
   ⭐ Popularity: {popularity:.3f}
   💡 Investment Score: {(affinity * 0.6 + (1-popularity) * 0.4):.3f}
    """

async def discover_cultural_tags(search_terms: str) -> List[str]:
    """Discover relevant Qloo tags for any cultural interests using tag search."""
    
    try:
        # Use Qloo's tag insights to find relevant tags
        params = {
            "filter.type": "urn:tag",
            "filter.tag.types": "urn:tag:keyword:place,urn:tag:cuisine,urn:tag:genre:place",
            "take": "50"
        }
        
        query_params = "&".join([f"{k}={v}" for k, v in params.items()])
        url = f"{QLOO_API_BASE}?{query_params}"
        
        data = await make_qloo_request(url)
        
        if "error" in data:
            return []
        
        tags = data.get('results', {}).get('tags', [])
        
        # Filter tags that match user's search terms (fuzzy matching)
        search_words = [term.strip().lower() for term in search_terms.split(',')]
        relevant_tags = []
        
        for tag in tags:
            tag_name = tag.get('name', '').lower()
            tag_id = tag.get('tag_id', '')
            
            # Check if any search word appears in tag name
            for search_word in search_words:
                if (search_word in tag_name or 
                    tag_name in search_word or 
                    any(word in tag_name for word in search_word.split()) or
                    any(word in search_word for word in tag_name.split())):
                    relevant_tags.append(tag_id)
                    break
        
        return relevant_tags[:5]  # Limit to top 5 most relevant
    except Exception as e:
        print(f"Tag discovery error: {e}")
        return []

def smart_tag_conversion(cultural_interests: str) -> List[str]:
    """Convert any cultural interests to potential Qloo tag formats.
    
    This function tries multiple strategies to convert user input to valid tags.
    Uses conservative, well-known tag patterns to avoid 400 errors.
    """
    
    interests_list = [interest.strip().lower() for interest in cultural_interests.split(",")]
    qloo_tags = []
    
    for interest in interests_list:
        # Strategy 1: Well-known cuisine types
        if any(word in interest for word in ['vegan', 'vegetarian']):
            qloo_tags.append("urn:tag:cuisine:vegetarian")
            
        elif any(word in interest for word in ['organic', 'farm']):
            qloo_tags.append("urn:tag:cuisine:organic")
            
        elif any(word in interest for word in ['italian']):
            qloo_tags.append("urn:tag:cuisine:italian")
            
        elif any(word in interest for word in ['japanese', 'sushi']):
            qloo_tags.append("urn:tag:cuisine:japanese")
            
        elif any(word in interest for word in ['mexican']):
            qloo_tags.append("urn:tag:cuisine:mexican")
            
        elif any(word in interest for word in ['indian']):
            qloo_tags.append("urn:tag:cuisine:indian")
            
        # Strategy 2: Place types (conservative approach)
        elif any(word in interest for word in ['restaurant', 'dining', 'food']):
            qloo_tags.append("urn:tag:genre:place:restaurant")
            
        elif any(word in interest for word in ['bar', 'pub']):
            qloo_tags.append("urn:tag:genre:place:bar")
            
        elif any(word in interest for word in ['cafe', 'coffee']):
            qloo_tags.append("urn:tag:genre:place:cafe")
            
        elif any(word in interest for word in ['music', 'concert', 'venue']):
            qloo_tags.append("urn:tag:genre:place:music_venue")
            
        elif any(word in interest for word in ['yoga', 'fitness', 'gym']):
            qloo_tags.append("urn:tag:genre:place:fitness")
            
        elif any(word in interest for word in ['shopping', 'retail', 'store']):
            qloo_tags.append("urn:tag:genre:place:shopping")
            
        elif any(word in interest for word in ['hotel', 'accommodation']):
            qloo_tags.append("urn:tag:genre:place:hotel")
            
        # Strategy 3: Simple keyword tags for everything else
        else:
            # Clean the interest and create a simple keyword tag
            clean_interest = interest.replace(' ', '_').replace('-', '_')
            qloo_tags.append(f"urn:tag:keyword:place:{clean_interest}")
    
    # Remove duplicates while preserving order
    return list(dict.fromkeys(qloo_tags))

def format_demographic_profile(demo_data: Dict) -> str:
    """Format demographic data into readable insights."""
    entity_id = demo_data.get('entity_id', 'Unknown')
    query_data = demo_data.get('query', {})
    
    age_data = query_data.get('age', {})
    gender_data = query_data.get('gender', {})
    
    # Find the most over-indexed age group
    top_age_group = max(age_data.items(), key=lambda x: x[1]) if age_data else ('unknown', 0)
    
    result = f"""
👥 **Demographic Profile** for {entity_id.split(':')[-1] if ':' in entity_id else entity_id}

📊 **Age Distribution:**"""
    
    for age_group, score in age_data.items():
        indicator = "🔥" if score > 0.2 else "📈" if score > 0 else "📉"
        result += f"\n   {indicator} {age_group.replace('_', ' ')}: {score:+.2f}"
    
    result += f"\n\n♂️♀️ **Gender Distribution:**"
    for gender, score in gender_data.items():
        indicator = "🔥" if abs(score) > 0.1 else "📊"
        result += f"\n   {indicator} {gender.capitalize()}: {score:+.2f}"
    
    # Investment insights
    young_professional_score = age_data.get('25_to_29', 0) + age_data.get('30_to_34', 0)
    result += f"\n\n💰 **Investment Relevance:**"
    result += f"\n   📈 Young Professional Index: {young_professional_score:.2f}"
    
    return result

@mcp.tool()
async def analyze_cultural_hotspots(city: str, cultural_interests: str = "artisanal food,indie music,third wave coffee") -> str:
    """Analyze cultural hotspots in a city to identify areas of high cultural activity.
    
    This is the foundation of CultureShift AI - identifying where cultural trends are concentrated.
    Works with ANY cultural interests - no need for predefined mappings!
    
    Args:
        city: City name (e.g. "New York", "Brooklyn", "San Francisco")  
        cultural_interests: ANY cultural interests in natural language (e.g. "vegan restaurants,jazz music,coworking spaces")
    """
    
    # Use smart tag conversion instead of hardcoded mapping
    qloo_tags = smart_tag_conversion(cultural_interests)
    
    # Try to discover additional relevant tags from Qloo's database
    discovered_tags = await discover_cultural_tags(cultural_interests)
    
    # Combine smart conversion + discovered tags
    all_tags = list(dict.fromkeys(qloo_tags + discovered_tags))  # Remove duplicates
    
    if not all_tags:
        # Fallback: create basic keyword tags
        interests_list = [interest.strip().replace(' ', '_') for interest in cultural_interests.split(",")]
        all_tags = [f"urn:tag:keyword:place:{interest}" for interest in interests_list]
    
    params = {
        "filter.type": "urn:heatmap",
        "filter.location.query": city,
        "signal.interests.tags": ",".join(all_tags[:5]),  # Limit to 5 most relevant tags
        "signal.demographics.age": "25_to_34",
        "output.heatmap.boundary": "neighborhood",
        "bias.trends": "true",
        "take": "20"
    }
    
    query_params = "&".join([f"{k}={v}" for k, v in params.items()])
    url = f"{QLOO_API_BASE}?{query_params}"
    
    data = await make_qloo_request(url)
    
    if "error" in data:
        return f"❌ Error analyzing cultural hotspots: {data['error']}"
    
    heatmap_data = data.get('results', {}).get('heatmap', [])
    
    if not heatmap_data:
        return f"No cultural hotspots found in {city} for interests: {cultural_interests}"
    
    # Sort by investment potential (high affinity, emerging popularity)
    sorted_hotspots = sorted(heatmap_data, 
                           key=lambda x: x.get('query', {}).get('affinity', 0) * 0.6 + 
                                       (1 - x.get('query', {}).get('popularity', 1)) * 0.4, 
                           reverse=True)
    
    result = f"🎯 **Cultural Hotspot Analysis for {city}**\n"
    result += f"🔍 **Analyzing:** {cultural_interests}\n"
    result += f"🏷️ **Generated Tags:** {', '.join([tag.split(':')[-1] for tag in all_tags[:5]])}\n"
    result += f"📊 **Found {len(heatmap_data)} hotspots**\n"
    result += "=" * 50 + "\n"
    
    # Show top 5 investment opportunities
    for i, hotspot in enumerate(sorted_hotspots[:5], 1):
        result += f"\n**#{i} Investment Opportunity:**"
        result += format_cultural_hotspot(hotspot)
        result += "\n" + "-" * 30
    
    return result

@mcp.tool()
async def analyze_demographic_profile(cultural_elements: str, location: str = "") -> str:
    """Analyze who is attracted to specific cultural elements or locations.
    
    This helps predict demographic movements and investment timing.
    Works with ANY cultural interests - no predefined mappings needed!
    
    Args:
        cultural_elements: ANY cultural interests in natural language (e.g. "sushi restaurants,rooftop bars,boutique fitness")
        location: Optional location context (e.g. "Brooklyn", "Lower East Side")
    """
    
    # Use smart tag conversion
    qloo_tags = smart_tag_conversion(cultural_elements)
    
    # Try to discover additional relevant tags
    discovered_tags = await discover_cultural_tags(cultural_elements)
    
    # Combine and limit tags
    all_tags = list(dict.fromkeys(qloo_tags + discovered_tags))[:5]
    
    if not all_tags:
        # Fallback
        elements_list = [elem.strip().replace(' ', '_') for elem in cultural_elements.split(",")]
        all_tags = [f"urn:tag:keyword:place:{elem}" for elem in elements_list]
    
    params = {
        "filter.type": "urn:demographics",
        "signal.interests.tags": ",".join(all_tags)
    }
    
    if location:
        params["signal.location.query"] = location
    
    query_params = "&".join([f"{k}={v}" for k, v in params.items()])
    url = f"{QLOO_API_BASE}?{query_params}"
    
    data = await make_qloo_request(url)
    
    if "error" in data:
        return f"❌ Error analyzing demographics: {data['error']}"
    
    demo_data = data.get('results', {}).get('demographics', [])
    
    if not demo_data:
        return f"No demographic data found for: {cultural_elements}"
    
    result = f"👥 **Demographic Analysis**\n"
    result += f"🔍 **Cultural Elements:** {cultural_elements}\n"
    result += f"🏷️ **Generated Tags:** {', '.join([tag.split(':')[-1] for tag in all_tags])}\n"
    if location:
        result += f"📍 **Location Context:** {location}\n"
    result += "=" * 50 + "\n"
    
    for demo_profile in demo_data:
        result += format_demographic_profile(demo_profile)
        result += "\n" + "-" * 40 + "\n"
    
    return result

@mcp.tool()
async def discover_available_tags(search_query: str) -> str:
    """Discover what cultural tags are available in Qloo's database for any search term.
    
    This tool helps users understand what cultural elements can be analyzed.
    
    Args:
        search_query: Any search term (e.g. "vegan", "techno", "coworking", "vintage")
    """
    
    discovered_tags = await discover_cultural_tags(search_query)
    
    if not discovered_tags:
        return f"No specific tags found for '{search_query}'. CultureShift AI will create intelligent keyword tags automatically."
    
    # Get detailed tag information
    result = f"🔍 **Available Cultural Tags for: '{search_query}'**\n"
    result += "=" * 50 + "\n"
    
    for i, tag_id in enumerate(discovered_tags, 1):
        tag_name = tag_id.split(':')[-1].replace('_', ' ').title()
        tag_type = tag_id.split(':')[2] if len(tag_id.split(':')) > 2 else 'keyword'
        result += f"{i}. **{tag_name}**\n"
        result += f"   🏷️ Type: {tag_type}\n"
        result += f"   🔗 ID: {tag_id}\n\n"
    
    result += "\n💡 **How to use:** Just use natural language like 'vegan restaurants' or 'techno clubs' - CultureShift AI will automatically convert them to the right tags!"
    
    return result

@mcp.tool()
async def analyze_neighborhood_culture(neighborhood: str, category: str = "restaurant,bar,cafe") -> str:
    """Analyze the cultural DNA of a specific neighborhood.
    
    This identifies what makes a neighborhood culturally distinct and attractive.
    
    Args:
        neighborhood: Specific neighborhood (e.g. "Williamsburg", "Lower East Side", "Mission District")
        category: Types of places to analyze (e.g. "restaurant,bar,cafe,shopping")
    """
    
    categories = [cat.strip() for cat in category.split(",")]
    
    all_results = []
    
    for cat in categories:
        params = {
            "filter.type": "urn:entity:place",
            "filter.tags": f"urn:tag:genre:place:{cat}",
            "signal.location.query": neighborhood,
            "signal.demographics.age": "25_to_34",
            "bias.trends": "true",
            "feature.explainability": "true",
            "take": "10"
        }
        
        query_params = "&".join([f"{k}={v}" for k, v in params.items()])
        url = f"{QLOO_API_BASE}?{query_params}"
        
        data = await make_qloo_request(url)
        
        if "error" not in data:
            entities = data.get('results', {}).get('entities', [])
            all_results.extend([(entity, cat) for entity in entities])
    
    if not all_results:
        return f"❌ No cultural data found for {neighborhood}"
    
    result = f"🏘️ **Cultural DNA Analysis: {neighborhood}**\n"
    result += f"🔍 **Categories Analyzed:** {', '.join(categories)}\n"
    result += f"📊 **Found {len(all_results)} cultural indicators**\n"
    result += "=" * 50 + "\n"
    
    # Group by category and show top places
    for cat in categories:
        cat_results = [(entity, c) for entity, c in all_results if c == cat]
        if cat_results:
            result += f"\n🎯 **{cat.upper()} Scene:**\n"
            
            for i, (entity, _) in enumerate(cat_results[:3], 1):
                name = entity.get('name', 'Unknown')
                popularity = entity.get('popularity', 0)
                tags = entity.get('tags', [])
                top_tags = [tag.get('name', '') for tag in tags[:3]]
                
                result += f"   {i}. **{name}**\n"
                result += f"      📊 Popularity: {popularity:.3f}\n"
                if top_tags:
                    result += f"      🏷️ Cultural Tags: {', '.join(top_tags)}\n"
                result += "\n"
    
    return result

if __name__ == "__main__":
    mcp.run()