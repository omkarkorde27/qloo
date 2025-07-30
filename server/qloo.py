from typing import Any, Dict, List, Optional, Union
import httpx
import os
from urllib.parse import quote_plus
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

# Load environment variables
load_dotenv()

# Initialize FastMCP server
mcp = FastMCP("cultureshift_ai")

# Constants
QLOO_API_BASE = "https://hackathon.api.qloo.com/v2/insights/"
USER_AGENT = "cultureshift-ai/1.0"

class QlooParameterBuilder:
    """Helper class to build and validate Qloo API parameters."""
    
    def __init__(self):
        self.params = {}
    
    def add_filter(self, key: str, value: Union[str, int, float, bool], required: bool = False):
        """Add a filter parameter with validation."""
        if value is not None:
            if isinstance(value, bool):
                self.params[f"filter.{key}"] = "true" if value else "false"
            else:
                self.params[f"filter.{key}"] = str(value)
        elif required:
            raise ValueError(f"Required parameter filter.{key} is missing")
        return self
    
    def add_signal(self, key: str, value: Union[str, int, float]):
        """Add a signal parameter."""
        if value is not None:
            self.params[f"signal.{key}"] = str(value)
        return self
    
    def add_output(self, key: str, value: Union[str, int, bool]):
        """Add an output parameter."""
        if value is not None:
            if isinstance(value, bool):
                self.params[f"{key}"] = "true" if value else "false"
            else:
                self.params[f"{key}"] = str(value)
        return self
    
    def build_url(self, base_url: str) -> str:
        """Build the complete URL with properly encoded parameters."""
        if not self.params:
            return base_url
        
        query_params = []
        for key, value in self.params.items():
            encoded_key = quote_plus(key)
            encoded_value = quote_plus(str(value))
            query_params.append(f"{encoded_key}={encoded_value}")
        
        return f"{base_url}?{'&'.join(query_params)}"

async def make_qloo_request(url: str) -> Dict[str, Any]:
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
            print(f"DEBUG: Calling URL: {url}")
            
            response = await client.get(url, headers=headers, timeout=30.0)
            print(f"DEBUG: Response status: {response.status_code}")
            
            if response.status_code == 400:
                response_text = response.text
                print(f"DEBUG: 400 Error response: {response_text}")
                return {"error": f"Bad Request - Invalid parameters. Response: {response_text[:500]}"}
            
            if response.status_code == 401:
                return {"error": "Unauthorized - Please check your API key"}
            
            if response.status_code == 429:
                return {"error": "Rate limit exceeded - Please try again later"}
            
            response.raise_for_status()
            return response.json()
            
        except httpx.TimeoutException:
            return {"error": "Request timeout - API took too long to respond"}
        except Exception as e:
            print(f"DEBUG: Exception occurred: {str(e)}")
            return {"error": f"API request failed: {str(e)}"}

def format_place_result(place: Dict, rank: int = None) -> str:
    """Format a place entity into readable string with investment insights."""
    name = place.get('name', 'Unknown Place')
    entity_id = place.get('entity_id', '')
    popularity = place.get('popularity', 0)
    
    # Extract properties
    properties = place.get('properties', {})
    address = properties.get('address', 'Address not available')
    business_rating = properties.get('business_rating')
    price_level = properties.get('price_level')
    
    # Extract location info
    geocode = properties.get('geocode', {})
    city = geocode.get('name', 'Unknown City')
    country = geocode.get('country_code', 'Unknown')
    
    # Extract tags for cultural context
    tags = place.get('tags', [])
    cultural_tags = [tag.get('name', '') for tag in tags[:5] if tag.get('name')]
    
    # Calculate investment metrics
    query_data = place.get('query', {})
    affinity_score = query_data.get('affinity', 0)
    
    # Investment scoring logic
    investment_score = 0
    if popularity > 0.8:
        investment_score += 3
    elif popularity > 0.6:
        investment_score += 2
    elif popularity > 0.4:
        investment_score += 1
    
    if affinity_score > 0.8:
        investment_score += 3
    elif affinity_score > 0.6:
        investment_score += 2
    
    investment_score = min(investment_score, 10)  # Cap at 10
    
    # Determine investment timeline
    if investment_score >= 8:
        timeline = "Immediate (0-6 months) - High activity area"
    elif investment_score >= 6:
        timeline = "Short-term (6-12 months) - Emerging potential"
    elif investment_score >= 4:
        timeline = "Medium-term (1-2 years) - Early indicators"
    else:
        timeline = "Long-term (2+ years) - Speculative"
    
    result = f"""
{'🏆' if rank == 1 else '🎯'} **{name}** {f'(#{rank})' if rank else ''}
📍 **Location:** {address}
🌍 **City:** {city}, {country}
📊 **Popularity:** {popularity:.3f} ({popularity*100:.1f}th percentile)
🔥 **Cultural Affinity:** {affinity_score:.3f}
💰 **Investment Score:** {investment_score}/10
⏰ **Timeline:** {timeline}"""

    if business_rating:
        result += f"\n⭐ **Business Rating:** {business_rating}/5"
    
    if price_level:
        dollar_signs = "$" * int(price_level)
        result += f"\n💵 **Price Level:** {dollar_signs} ({price_level}/4)"
    
    if cultural_tags:
        result += f"\n🏷️ **Cultural Tags:** {', '.join(cultural_tags)}"
    
    return result

async def discover_qloo_tags(search_terms: str, tag_types: str = "urn:tag:cuisine,urn:tag:genre:place,urn:tag:category:place") -> List[str]:
    """Dynamically discover relevant Qloo tags using their tag search API."""
    
    try:
        builder = QlooParameterBuilder()
        builder.add_filter("type", "urn:tag")
        builder.add_filter("tag.types", tag_types)
        builder.add_output("take", 100)  # Get more tags for better matching
        
        url = builder.build_url(QLOO_API_BASE)
        data = await make_qloo_request(url)
        
        if "error" in data:
            print(f"Tag discovery error: {data['error']}")
            return []
        
        tags = data.get('results', {}).get('tags', [])
        search_words = [term.strip().lower() for term in search_terms.split(',')]
        relevant_tags = []
        
        for tag in tags:
            tag_name = tag.get('name', '').lower()
            tag_id = tag.get('tag_id', '')
            
            # Score each tag based on relevance to search terms
            relevance_score = 0
            for search_word in search_words:
                # Exact match gets highest score
                if search_word == tag_name:
                    relevance_score += 10
                # Contains search word gets high score
                elif search_word in tag_name or tag_name in search_word:
                    relevance_score += 5
                # Word-level matching gets medium score
                elif any(word in tag_name for word in search_word.split()):
                    relevance_score += 3
                elif any(word in search_word for word in tag_name.split()):
                    relevance_score += 2
            
            if relevance_score > 0:
                relevant_tags.append((tag_id, tag_name, relevance_score))
        
        # Sort by relevance score and return top matches
        relevant_tags.sort(key=lambda x: x[2], reverse=True)
        return [tag[0] for tag in relevant_tags[:10]]  # Return top 10 most relevant
        
    except Exception as e:
        print(f"Tag discovery error: {e}")
        return []

async def smart_tag_conversion(cultural_interests: str) -> List[str]:
    """Dynamically convert any cultural interests to Qloo tags using API discovery."""
    if not cultural_interests:
        return []
    
    # Step 1: Try to discover existing tags from Qloo's database
    discovered_tags = await discover_qloo_tags(cultural_interests)
    
    if discovered_tags:
        print(f"Found {len(discovered_tags)} relevant tags from Qloo database")
        return discovered_tags
    
    # Step 2: If no tags found, create intelligent keyword tags
    interests_list = [interest.strip().lower() for interest in cultural_interests.split(",")]
    fallback_tags = []
    
    for interest in interests_list:
        # Clean and structure the interest
        clean_interest = interest.replace(' ', '_').replace('-', '_').replace('&', 'and')
        
        # Try different tag type patterns based on context clues
        if any(word in interest for word in ['cuisine', 'food', 'restaurant', 'dining']):
            # Food-related interests
            cuisine_name = interest.replace('cuisine', '').replace('food', '').replace('restaurant', '').strip()
            cuisine_name = cuisine_name.replace(' ', '_')
            if cuisine_name:
                fallback_tags.append(f"urn:tag:cuisine:{cuisine_name}")
        
        elif any(word in interest for word in ['bar', 'club', 'venue', 'hotel', 'cafe', 'shop', 'store']):
            # Place type interests
            fallback_tags.append(f"urn:tag:genre:place:{clean_interest}")
        
        else:
            # Generic keyword tag
            fallback_tags.append(f"urn:tag:keyword:place:{clean_interest}")
    
    return fallback_tags

async def validate_and_optimize_tags(tags: List[str], location: str = "") -> List[str]:
    """Validate tags by making a test query and optimize for best results."""
    if not tags:
        return []
    
    # Test the tags with a simple query to see if they return results
    validated_tags = []
    
    for tag in tags[:5]:  # Test up to 5 tags to avoid rate limiting
        try:
            builder = QlooParameterBuilder()
            builder.add_filter("type", "urn:entity:place")
            builder.add_filter("tags", tag)
            if location:
                builder.add_signal("location.query", location)
            builder.add_output("take", 1)  # Just check if any results exist
            
            url = builder.build_url(QLOO_API_BASE)
            data = await make_qloo_request(url)
            
            # If the tag returns results, it's valid
            if "error" not in data and data.get('results', {}).get('entities'):
                validated_tags.append(tag)
                print(f"✅ Validated tag: {tag}")
            else:
                print(f"❌ Invalid tag: {tag}")
                
        except Exception as e:
            print(f"Tag validation error for {tag}: {e}")
            continue
    
    return validated_tags if validated_tags else tags  # Return original if validation fails

@mcp.tool()
async def analyze_places_comprehensive(
    location: str,
    cultural_interests: str = "artisanal food,third wave coffee",
    place_types: str = "restaurant,cafe,bar",
    max_results: int = 10,
    min_popularity: float = 0.0,
    max_popularity: float = 1.0,
    min_price_level: Optional[int] = None,
    max_price_level: Optional[int] = None,
    min_business_rating: Optional[float] = None,
    max_business_rating: Optional[float] = None,
    demographics_age: str = "25_to_29",
    sort_by: str = "affinity",
    include_explainability: bool = True
) -> str:
    """Comprehensive place analysis with full parameter support for CultureShift AI.
    
    This is the core function for analyzing places with investment potential.
    
    Args:
        location: Location to analyze (e.g., "Brooklyn", "Lower East Side", "San Francisco")
        cultural_interests: Cultural elements to focus on (e.g., "vegan restaurants,craft cocktails")
        place_types: Types of places to include (e.g., "restaurant,bar,cafe,hotel")
        max_results: Maximum number of results (1-50)
        min_popularity: Minimum popularity score (0.0-1.0)
        max_popularity: Maximum popularity score (0.0-1.0)
        min_price_level: Minimum price level (1-4)
        max_price_level: Maximum price level (1-4)
        min_business_rating: Minimum business rating (1.0-5.0)
        max_business_rating: Maximum business rating (1.0-5.0)
        demographics_age: Target age group (25_to_29, 30_to_34, etc.)
        sort_by: Sort results by ("affinity" or "distance")
        include_explainability: Include explainability data in response
    """
    
    try:
        # Build parameters using the parameter builder
        builder = QlooParameterBuilder()
        
        # Required parameters
        builder.add_filter("type", "urn:entity:place", required=True)
        
        # Location parameters
        builder.add_signal("location.query", location)
        
        # Cultural interests and place types - Use dynamic tag discovery
        cultural_tags = await smart_tag_conversion(cultural_interests)
        place_type_tags = await smart_tag_conversion(place_types)
        
        # Validate tags for better results
        if location:
            cultural_tags = await validate_and_optimize_tags(cultural_tags, location)
            place_type_tags = await validate_and_optimize_tags(place_type_tags, location)
        
        all_tags = cultural_tags + place_type_tags
        
        if all_tags:
            builder.add_filter("tags", ",".join(all_tags[:10]))  # Limit to 10 tags
            builder.add_signal("interests.tags", ",".join(cultural_tags[:5]))
        
        # Popularity filters
        if min_popularity > 0:
            builder.add_filter("popularity.min", min_popularity)
        if max_popularity < 1:
            builder.add_filter("popularity.max", max_popularity)
        
        # Price level filters
        if min_price_level is not None:
            builder.add_filter("price_level.min", min_price_level)
        if max_price_level is not None:
            builder.add_filter("price_level.max", max_price_level)
        
        # Business rating filters
        if min_business_rating is not None:
            builder.add_filter("properties.business_rating.min", min_business_rating)
        if max_business_rating is not None:
            builder.add_filter("properties.business_rating.max", max_business_rating)
        
        # Demographics
        builder.add_signal("demographics.age", demographics_age)
        
        # Output parameters
        builder.add_output("take", min(max_results, 50))
        builder.add_output("sort_by", sort_by)
        if include_explainability:
            builder.add_output("feature.explainability", True)
        
        # Build URL and make request
        url = builder.build_url(QLOO_API_BASE)
        data = await make_qloo_request(url)
        
        if "error" in data:
            return f"❌ **Error analyzing places:** {data['error']}"
        
        entities = data.get('results', {}).get('entities', [])
        
        if not entities:
            return f"❌ **No places found** matching your criteria in {location}"
        
        # Format results
        result = f"🏙️ **CultureShift AI - Place Analysis Report**\n"
        result += f"📍 **Location:** {location}\n"
        result += f"🎯 **Cultural Focus:** {cultural_interests}\n"
        result += f"🏢 **Place Types:** {place_types}\n"
        result += f"📊 **Found:** {len(entities)} places\n"
        result += f"🎚️ **Popularity Range:** {min_popularity:.1f} - {max_popularity:.1f}\n"
        if min_price_level or max_price_level:
            result += f"💰 **Price Range:** {min_price_level or 1} - {max_price_level or 4}\n"
        result += "=" * 60 + "\n"
        
        # Calculate average metrics for summary
        avg_popularity = sum(p.get('popularity', 0) for p in entities) / len(entities)
        high_potential_count = sum(1 for p in entities if p.get('popularity', 0) > 0.7)
        
        result += f"\n📈 **Investment Summary:**\n"
        result += f"   • Average Popularity: {avg_popularity:.3f}\n"
        result += f"   • High Potential Places: {high_potential_count}/{len(entities)}\n"
        result += f"   • Recommended Timeline: {'Immediate' if avg_popularity > 0.8 else 'Short-term' if avg_popularity > 0.6 else 'Medium-term'}\n"
        
        result += "\n🎯 **Top Investment Opportunities:**\n"
        result += "=" * 60 + "\n"
        
        # Show detailed results
        for i, place in enumerate(entities, 1):
            result += format_place_result(place, i)
            result += "\n" + "-" * 50 + "\n"
        
        # Add query insights if available
        query_info = data.get('query', {})
        if query_info:
            locality_info = query_info.get('locality', {})
            if locality_info:
                result += f"\n📍 **Location Matched:** {locality_info.get('name', 'Unknown')}\n"
        
        return result
        
    except ValueError as e:
        return f"❌ **Parameter Error:** {str(e)}"
    except Exception as e:
        return f"❌ **Unexpected Error:** {str(e)}"

@mcp.tool()
async def search_places_by_criteria(
    location: str,
    cuisine_type: str = "",
    price_range: str = "1-4",
    rating_min: float = 0.0,
    must_be_open: str = "",
    external_ratings: str = "",
    party_size: Optional[int] = None,
    hotel_class: Optional[str] = None,
    max_results: int = 15
) -> str:
    """Search for places using specific business criteria for investment analysis.
    
    Args:
        location: Location to search (neighborhood, city, or address)
        cuisine_type: Specific cuisine (italian, japanese, vegan, etc.)
        price_range: Price range as "min-max" (e.g., "2-4" for $$ to $$$$)
        rating_min: Minimum business rating (0.0-5.0)
        must_be_open: Day place must be open (Monday, Tuesday, etc.)
        external_ratings: External rating source (resy, tripadvisor, michelin)
        party_size: Required party size accommodation
        hotel_class: Hotel class range "min-max" (e.g., "3-5")
        max_results: Maximum results to return
    """
    
    try:
        builder = QlooParameterBuilder()
        builder.add_filter("type", "urn:entity:place", required=True)
        builder.add_signal("location.query", location)
        
        # Handle cuisine type - Use dynamic discovery
        if cuisine_type:
            cuisine_tags = await smart_tag_conversion(cuisine_type)
            if location:
                cuisine_tags = await validate_and_optimize_tags(cuisine_tags, location)
            if cuisine_tags:
                builder.add_filter("tags", ",".join(cuisine_tags))
        
        # Handle price range
        if price_range and "-" in price_range:
            try:
                min_price, max_price = map(int, price_range.split("-"))
                builder.add_filter("price_level.min", min_price)
                builder.add_filter("price_level.max", max_price)
            except ValueError:
                pass
        
        # Rating filter
        if rating_min > 0:
            builder.add_filter("properties.business_rating.min", rating_min)
        
        # Hours filter
        if must_be_open:
            builder.add_filter("hours", must_be_open)
        
        # External ratings
        if external_ratings:
            builder.add_filter("external.exists", external_ratings)
        
        # Party size for restaurants
        if party_size:
            builder.add_filter("external.resy.party_size.min", party_size)
        
        # Hotel class
        if hotel_class and "-" in hotel_class:
            try:
                min_class, max_class = map(int, hotel_class.split("-"))
                builder.add_filter("hotel_class.min", min_class)
                builder.add_filter("hotel_class.max", max_class)
            except ValueError:
                pass
        
        builder.add_output("take", min(max_results, 50))
        builder.add_output("sort_by", "affinity")
        
        url = builder.build_url(QLOO_API_BASE)
        data = await make_qloo_request(url)
        
        if "error" in data:
            return f"❌ **Search Error:** {data['error']}"
        
        entities = data.get('results', {}).get('entities', [])
        
        if not entities:
            return f"❌ **No places found** matching your specific criteria in {location}"
        
        result = f"🔍 **Targeted Place Search Results**\n"
        result += f"📍 **Location:** {location}\n"
        if cuisine_type:
            result += f"🍽️ **Cuisine:** {cuisine_type}\n"
        if price_range != "1-4":
            result += f"💰 **Price Range:** {price_range}\n"
        if rating_min > 0:
            result += f"⭐ **Min Rating:** {rating_min}+\n"
        result += f"📊 **Results:** {len(entities)} places found\n"
        result += "=" * 50 + "\n"
        
        for i, place in enumerate(entities, 1):
            result += format_place_result(place, i)
            result += "\n" + "-" * 40 + "\n"
        
        return result
        
    except Exception as e:
        return f"❌ **Search Error:** {str(e)}"

# Legacy tools converted to use new dynamic system
@mcp.tool()
async def analyze_cultural_hotspots(city: str, cultural_interests: str = "artisanal food,indie music,third wave coffee") -> str:
    """Analyze cultural hotspots in a city using heatmap data - now with dynamic tag discovery.
    
    This creates geographic heatmaps showing cultural activity concentration.
    
    Args:
        city: City name (e.g. "New York", "Brooklyn", "San Francisco")  
        cultural_interests: ANY cultural interests in natural language
    """
    
    try:
        # Use dynamic tag discovery
        cultural_tags = await smart_tag_conversion(cultural_interests)
        
        # Validate tags for better results
        if city:
            cultural_tags = await validate_and_optimize_tags(cultural_tags, city)
        
        if not cultural_tags:
            # Fallback: create basic keyword tags
            interests_list = [interest.strip().replace(' ', '_') for interest in cultural_interests.split(",")]
            cultural_tags = [f"urn:tag:keyword:place:{interest}" for interest in interests_list]
        
        builder = QlooParameterBuilder()
        builder.add_filter("type", "urn:heatmap")
        builder.add_filter("location.query", city)
        builder.add_signal("interests.tags", ",".join(cultural_tags[:5]))
        builder.add_signal("demographics.age", "25_to_29")
        builder.add_output("output.heatmap.boundary", "neighborhood")
        builder.add_output("take", 20)
        
        url = builder.build_url(QLOO_API_BASE)
        data = await make_qloo_request(url)
        
        if "error" in data:
            return f"❌ Error analyzing cultural hotspots: {data['error']}"
        
        heatmap_data = data.get('results', {}).get('heatmap', [])
        
        if not heatmap_data:
            return f"❌ No cultural hotspots found in {city} for interests: {cultural_interests}"
        
        # Sort by investment potential (high affinity, emerging popularity)
        sorted_hotspots = sorted(heatmap_data, 
                               key=lambda x: x.get('query', {}).get('affinity', 0) * 0.6 + 
                                           (1 - x.get('query', {}).get('popularity', 1)) * 0.4, 
                               reverse=True)
        
        result = f"🗺️ **Cultural Heatmap Analysis for {city}**\n"
        result += f"🔍 **Analyzing:** {cultural_interests}\n"
        result += f"🏷️ **Generated Tags:** {', '.join([tag.split(':')[-1] for tag in cultural_tags[:5]])}\n"
        result += f"📊 **Found {len(heatmap_data)} hotspots**\n"
        result += "=" * 60 + "\n"
        
        # Show top 5 investment opportunities
        for i, hotspot in enumerate(sorted_hotspots[:5], 1):
            location = hotspot.get('location', {})
            query_data = hotspot.get('query', {})
            
            lat = location.get('latitude', 'Unknown')
            lng = location.get('longitude', 'Unknown')
            geohash = location.get('geohash', 'Unknown')
            
            affinity = query_data.get('affinity', 0)
            affinity_rank = query_data.get('affinity_rank', 0)
            popularity = query_data.get('popularity', 0)
            investment_score = affinity * 0.6 + (1-popularity) * 0.4
            
            result += f"\n🎯 **#{i} Cultural Hotspot** ({geohash})\n"
            result += f"   📍 Coordinates: {lat}, {lng}\n"
            result += f"   🔥 Cultural Affinity: {affinity:.3f}\n"
            result += f"   📊 Affinity Rank: {affinity_rank:.3f}\n"
            result += f"   ⭐ Popularity: {popularity:.3f}\n"
            result += f"   💰 Investment Score: {investment_score:.3f}\n"
            result += f"   ⏰ Timeline: {'Immediate' if investment_score > 0.8 else 'Short-term' if investment_score > 0.6 else 'Medium-term'}\n"
            result += "-" * 50 + "\n"
        
        return result
        
    except Exception as e:
        return f"❌ **Heatmap Analysis Error:** {str(e)}"

@mcp.tool()
async def analyze_demographic_profile(cultural_elements: str, location: str = "") -> str:
    """Analyze who is attracted to specific cultural elements - now with dynamic discovery.
    
    This helps predict demographic movements and investment timing.
    
    Args:
        cultural_elements: ANY cultural interests in natural language
        location: Optional location context
    """
    
    try:
        # Use dynamic tag conversion
        cultural_tags = await smart_tag_conversion(cultural_elements)
        
        # Validate tags if location provided
        if location:
            cultural_tags = await validate_and_optimize_tags(cultural_tags, location)
        
        if not cultural_tags:
            # Fallback
            elements_list = [elem.strip().replace(' ', '_') for elem in cultural_elements.split(",")]
            cultural_tags = [f"urn:tag:keyword:place:{elem}" for elem in elements_list]
        
        builder = QlooParameterBuilder()
        builder.add_filter("type", "urn:demographics")
        builder.add_signal("interests.tags", ",".join(cultural_tags[:5]))
        
        if location:
            builder.add_signal("location.query", location)
        
        url = builder.build_url(QLOO_API_BASE)
        data = await make_qloo_request(url)
        
        if "error" in data:
            return f"❌ Error analyzing demographics: {data['error']}"
        
        demo_data = data.get('results', {}).get('demographics', [])
        
        if not demo_data:
            return f"❌ No demographic data found for: {cultural_elements}"
        
        result = f"👥 **Demographic Analysis Report**\n"
        result += f"🔍 **Cultural Elements:** {cultural_elements}\n"
        result += f"🏷️ **Generated Tags:** {', '.join([tag.split(':')[-1] for tag in cultural_tags])}\n"
        if location:
            result += f"📍 **Location Context:** {location}\n"
        result += "=" * 60 + "\n"
        
        for demo_profile in demo_data:
            entity_id = demo_profile.get('entity_id', 'Unknown')
            query_data = demo_profile.get('query', {})
            
            age_data = query_data.get('age', {})
            gender_data = query_data.get('gender', {})
            
            result += f"\n👥 **Demographic Profile** for {entity_id.split(':')[-1] if ':' in entity_id else entity_id}\n"
            
            result += f"\n📊 **Age Distribution:**"
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
            result += f"\n   🎯 Investment Timeline: {'Immediate' if young_professional_score > 0.4 else 'Short-term' if young_professional_score > 0.2 else 'Medium-term'}"
            result += "\n" + "-" * 50 + "\n"
        
        return result
        
    except Exception as e:
        return f"❌ **Demographic Analysis Error:** {str(e)}"

@mcp.tool()
async def analyze_neighborhood_culture(neighborhood: str, category: str = "restaurant,bar,cafe") -> str:
    """Analyze the cultural DNA of a specific neighborhood - now with dynamic discovery.
    
    Args:
        neighborhood: Specific neighborhood name
        category: Types of places to analyze (comma-separated)
    """
    
    try:
        categories = [cat.strip() for cat in category.split(",")]
        all_results = []
        
        for cat in categories:
            # Use dynamic tag conversion for categories
            cat_tags = await smart_tag_conversion(cat)
            if not cat_tags:
                cat_tags = [f"urn:tag:genre:place:{cat}"]
            
            builder = QlooParameterBuilder()
            builder.add_filter("type", "urn:entity:place")
            builder.add_filter("tags", ",".join(cat_tags))
            builder.add_signal("location.query", neighborhood)
            builder.add_signal("demographics.age", "25_to_29")
            builder.add_output("feature.explainability", True)
            builder.add_output("take", 10)
            
            url = builder.build_url(QLOO_API_BASE)
            data = await make_qloo_request(url)
            
            if "error" not in data:
                entities = data.get('results', {}).get('entities', [])
                all_results.extend([(entity, cat) for entity in entities])
        
        if not all_results:
            return f"❌ No cultural data found for {neighborhood}"
        
        result = f"🏘️ **Cultural DNA Analysis: {neighborhood}**\n"
        result += f"🔍 **Categories Analyzed:** {', '.join(categories)}\n"
        result += f"📊 **Found {len(all_results)} cultural indicators**\n"
        result += "=" * 60 + "\n"
        
        # Calculate overall neighborhood metrics
        avg_popularity = sum(entity[0].get('popularity', 0) for entity in all_results) / len(all_results)
        result += f"\n📈 **Neighborhood Overview:**\n"
        result += f"   • Average Cultural Popularity: {avg_popularity:.3f}\n"
        result += f"   • Investment Potential: {'High' if avg_popularity > 0.7 else 'Medium' if avg_popularity > 0.5 else 'Emerging'}\n"
        
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
        
    except Exception as e:
        return f"❌ **Neighborhood Analysis Error:** {str(e)}"