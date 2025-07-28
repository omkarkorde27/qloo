from typing import Any, Dict, List, Optional, Tuple, Union
import httpx
import os
import re
from datetime import datetime
from enum import Enum
import json
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

# Load environment variables
load_dotenv()

# Initialize FastMCP server
mcp = FastMCP("qloo")

# Constants - Updated to correct API base
QLOO_API_BASE = "https://hackathon.api.qloo.com/v2"
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

class QlooUseCase(Enum):
    """Qloo API use cases based on official documentation"""
    RECOMMENDATION_INSIGHTS = "recommendation_insights"  # Get recommendations for entity types
    DEMOGRAPHIC_INSIGHTS = "demographic_insights"       # Demographic data for entities/tags
    HEATMAPS = "heatmaps"                               # Geographic affinity visualization
    LOCATION_BASED_INSIGHTS = "location_based_insights" # Location-tailored recommendations
    TASTE_ANALYSIS = "taste_analysis"                   # Tag metadata and taste analysis

# =============================================================================
# QUERY CLASSIFICATION AND ENDPOINT MAPPING
# =============================================================================

def classify_user_query(query: str) -> Tuple[QlooUseCase, Dict[str, Any]]:
    """Classify user query into Qloo use cases and extract parameters"""
    query_lower = query.lower()
    
    # Extract location
    location_match = re.search(r'in\s+([A-Za-z\s,]+?)(?:\s|$|for|with)', query)
    location = location_match.group(1).strip() if location_match else ""
    
    # Heatmap patterns
    heatmap_patterns = [
        r'(heatmap|heat\s*map|geographic|geo|mapping)',
        r'(visuali[sz]e|map\s+data|geographic\s+data)',
        r'(affinity\s+map|location\s+data)'
    ]
    
    # Demographic patterns
    demographic_patterns = [
        r'(demographic|audience|age|gender)',
        r'(who\s+likes|audience\s+for|popular\s+with)',
        r'(age\s+group|gender\s+breakdown|demographic\s+data)'
    ]
    
    # Cultural/taste analysis patterns
    taste_patterns = [
        r'(cultural\s+tag|taste|characteristic|metadata)',
        r'(tag\s+analysis|cultural\s+insight|taste\s+profile)',
        r'(what\s+defines|characteristics\s+of)'
    ]
    
    # Location-based patterns (different from heatmaps)
    location_based_patterns = [
        r'(popular\s+in|trending\s+in|specific\s+to)',
        r'(location\s+based|area\s+specific|regional)',
        r'(local\s+preferences|area\s+recommendations)'
    ]
    
    # Restaurant/place patterns
    recommendation_patterns = [
        r'(restaurant|food|dining|eat|place|venue|bar|cafe)',
        r'(recommend|suggestion|find|looking\s+for)',
        r'(japanese|italian|chinese|indian|mexican|thai|french|korean)',
        r'(museum|park|theater|cinema|shopping|entertainment)'
    ]
    
    # Classify based on patterns
    if any(re.search(pattern, query_lower) for pattern in heatmap_patterns):
        use_case = QlooUseCase.HEATMAPS
    elif any(re.search(pattern, query_lower) for pattern in demographic_patterns):
        use_case = QlooUseCase.DEMOGRAPHIC_INSIGHTS
    elif any(re.search(pattern, query_lower) for pattern in taste_patterns):
        use_case = QlooUseCase.TASTE_ANALYSIS
    elif any(re.search(pattern, query_lower) for pattern in location_based_patterns) and location:
        use_case = QlooUseCase.LOCATION_BASED_INSIGHTS
    else:
        # Default to recommendations
        use_case = QlooUseCase.RECOMMENDATION_INSIGHTS
    
    return use_case, {
        "location": location,
        "query": query,
        "query_lower": query_lower
    }

def build_qloo_parameters(use_case: QlooUseCase, params: Dict[str, Any], 
                         social_context: str = "friends") -> Dict[str, Any]:
    """Build Qloo API parameters based on use case and query parameters"""
    
    query_text = params.get("query_lower", "")
    location = params.get("location", "")
    
    if use_case == QlooUseCase.RECOMMENDATION_INSIGHTS:
        # Determine entity type and comprehensive parameters
        entity_type, entity_params = _determine_entity_and_comprehensive_params(query_text)
        
        # Start with entity-specific parameters
        qloo_params = entity_params.copy()
        
        # Add location if available
        if location:
            qloo_params["filter.location.query"] = location
        
        # Add social context influence
        demographic_signals = _get_demographic_signals(social_context)
        qloo_params.update(demographic_signals)
        
    elif use_case == QlooUseCase.DEMOGRAPHIC_INSIGHTS:
        qloo_params = {
            "filter.type": "urn:demographics"
        }
        
        # Determine what to analyze demographically
        entity_type, entity_params = _determine_entity_and_comprehensive_params(query_text)
        
        # Extract tags for signal
        if "filter.tags" in entity_params:
            qloo_params["signal.interests.tags"] = entity_params["filter.tags"]
        
        # If asking about a specific place/entity
        if "restaurant" in query_text or "place" in query_text:
            # Would need entity ID resolution here in real implementation
            pass
            
    elif use_case == QlooUseCase.HEATMAPS:
        qloo_params = {
            "filter.type": "urn:heatmap"
        }
        
        if location:
            qloo_params["filter.location.query"] = location
        
        # Add interest signals based on query
        entity_type, entity_params = _determine_entity_and_comprehensive_params(query_text)
        if "filter.tags" in entity_params:
            qloo_params["signal.interests.tags"] = entity_params["filter.tags"]
            
    elif use_case == QlooUseCase.LOCATION_BASED_INSIGHTS:
        entity_type, entity_params = _determine_entity_and_comprehensive_params(query_text)
        
        # Start with entity-specific parameters
        qloo_params = entity_params.copy()
        qloo_params["signal.location.query"] = location
        
        # Move tags to signal for location-based insights
        if "filter.tags" in qloo_params:
            qloo_params["signal.interests.tags"] = qloo_params["filter.tags"]
            del qloo_params["filter.tags"]
            
    elif use_case == QlooUseCase.TASTE_ANALYSIS:
        qloo_params = {
            "filter.type": "urn:tag"
        }
        
        # Determine tag types to analyze
        if "media" in query_text or "movie" in query_text or "tv" in query_text:
            qloo_params["filter.tag.types"] = "urn:tag:keyword:media"
            qloo_params["filter.parents.types"] = "urn:entity:movie,urn:entity:tv_show"
        elif "place" in query_text or "restaurant" in query_text:
            qloo_params["filter.tag.types"] = "urn:tag:genre:place"
            qloo_params["filter.parents.types"] = "urn:entity:place"
        
        if location:
            qloo_params["signal.location.query"] = location
    
    return qloo_params

def _determine_entity_and_comprehensive_params(query_text: str) -> Tuple[str, Dict[str, Any]]:
    """Determine entity type and build comprehensive parameters from query text"""
    
    params = {}
    
    # =============================================================================
    # PERSON ENTITY (Fixed priority and parameter mapping)
    # =============================================================================
    if any(word in query_text for word in ["director", "actor", "actress", "celebrity", "person", "politician", "athlete", "author", "writer", "musician", "singer"]):
        entity_type = "urn:entity:person"
        params["filter.type"] = entity_type
        
        # Gender filter (Fixed logic)
        if any(word in query_text for word in ["female", "women", "woman", "actress"]):
            params["filter.gender"] = "female"
        elif any(word in query_text for word in ["male", "men", "man", "actor"]):
            params["filter.gender"] = "male"
            
        # Birth year filters
        if "born after" in query_text:
            year_match = re.search(r'born after\s+(\d{4})', query_text)
            if year_match:
                year = year_match.group(1)
                params["filter.date_of_birth.min"] = f"{year}-01-01"
        elif "born before" in query_text:
            year_match = re.search(r'born before\s+(\d{4})', query_text)
            if year_match:
                year = year_match.group(1)
                params["filter.date_of_birth.max"] = f"{year}-12-31"
        elif "born in" in query_text:
            year_match = re.search(r'born in\s+(\d{4})', query_text)
            if year_match:
                year = year_match.group(1)
                params["filter.date_of_birth.min"] = f"{year}-01-01"
                params["filter.date_of_birth.max"] = f"{year}-12-31"
                
        # Age-based filters (alternative approach)
        if "young" in query_text or "under 30" in query_text:
            params["filter.date_of_birth.min"] = "1990-01-01"
        elif "veteran" in query_text or "experienced" in query_text or "older" in query_text:
            params["filter.date_of_birth.max"] = "1970-01-01"
            
        # Popularity filters
        if any(word in query_text for word in ["famous", "well-known", "popular", "renowned"]):
            params["filter.popularity.min"] = "0.7"
        elif any(word in query_text for word in ["emerging", "up-and-coming", "unknown"]):
            params["filter.popularity.max"] = "0.5"
            
        # Trends bias
        if any(word in query_text for word in ["trending", "viral", "hot", "current"]):
            params["bias.trends"] = "high"
            
        # Profession tags (using supported format)
        person_tags = []
        if "director" in query_text:
            person_tags.append("urn:tag:profession:director")
        if any(word in query_text for word in ["actor", "actress"]):
            person_tags.append("urn:tag:profession:actor")
        if any(word in query_text for word in ["musician", "singer"]):
            person_tags.append("urn:tag:profession:musician")
        if "politician" in query_text:
            person_tags.append("urn:tag:profession:politician")
        if any(word in query_text for word in ["athlete", "sports"]):
            person_tags.append("urn:tag:profession:athlete")
        if any(word in query_text for word in ["author", "writer"]):
            person_tags.append("urn:tag:profession:author")
            
        if person_tags:
            params["filter.tags"] = ",".join(person_tags)
            
        # External platform filters
        if "instagram" in query_text:
            params["filter.external.exists"] = "instagram"
        elif "twitter" in query_text:
            params["filter.external.exists"] = "twitter"
        elif "imdb" in query_text:
            params["filter.external.exists"] = "imdb"
            
    # =============================================================================
    # MOVIE ENTITY
    # =============================================================================
    elif any(word in query_text for word in ["movie", "film", "cinema", "blockbuster", "flick"]):
        entity_type = "urn:entity:movie"
        params["filter.type"] = entity_type
        
        # Release year filters
        year_match = re.search(r'(19|20)\d{2}', query_text)
        if year_match:
            year = year_match.group()
            params["filter.release_year.min"] = year
            
        if any(word in query_text for word in ["recent", "new", "latest"]):
            params["filter.release_year.min"] = "2020"
        elif "classic" in query_text:
            params["filter.release_year.max"] = "1990"
            
        # Content rating filters
        if any(word in query_text for word in ["family", "kids", "children"]):
            params["filter.content_rating"] = "G,PG"
        elif any(word in query_text for word in ["teen", "teenager"]):
            params["filter.content_rating"] = "PG-13"
        elif any(word in query_text for word in ["mature", "adult"]):
            params["filter.content_rating"] = "R"
            
        # Rating filters
        if any(word in query_text for word in ["highly rated", "top rated", "best"]):
            params["filter.rating.min"] = "4.0"
        elif "good" in query_text:
            params["filter.rating.min"] = "3.5"
            
        # Popularity filters
        if any(word in query_text for word in ["blockbuster", "popular", "hit"]):
            params["filter.popularity.min"] = "0.7"
        elif any(word in query_text for word in ["indie", "independent"]):
            params["filter.popularity.max"] = "0.5"
            
        # Trends bias
        if any(word in query_text for word in ["trending", "viral", "hot"]):
            params["bias.trends"] = "high"
            
        # Genre tags
        movie_tags = []
        if "action" in query_text:
            movie_tags.append("urn:tag:genre:media:action")
        if "comedy" in query_text:
            movie_tags.append("urn:tag:genre:media:comedy")
        if "drama" in query_text:
            movie_tags.append("urn:tag:genre:media:drama")
        if "horror" in query_text:
            movie_tags.append("urn:tag:genre:media:horror")
        if any(word in query_text for word in ["romance", "romantic"]):
            movie_tags.append("urn:tag:genre:media:romance")
        if "thriller" in query_text:
            movie_tags.append("urn:tag:genre:media:thriller")
        if any(word in query_text for word in ["sci-fi", "science fiction"]):
            movie_tags.append("urn:tag:genre:media:science_fiction")
        if "fantasy" in query_text:
            movie_tags.append("urn:tag:genre:media:fantasy")
        if "documentary" in query_text:
            movie_tags.append("urn:tag:genre:media:documentary")
        if any(word in query_text for word in ["animation", "animated"]):
            movie_tags.append("urn:tag:genre:media:animation")
            
        if movie_tags:
            params["filter.tags"] = ",".join(movie_tags)
            
    # =============================================================================
    # TV SHOW ENTITY
    # =============================================================================
    elif any(word in query_text for word in ["tv", "show", "series", "television", "netflix", "streaming", "episode"]):
        entity_type = "urn:entity:tv_show"
        params["filter.type"] = entity_type
        
        # Release year filters
        if any(word in query_text for word in ["recent", "new", "latest"]):
            params["filter.release_year.min"] = "2020"
        elif "classic" in query_text:
            params["filter.release_year.max"] = "2000"
            
        # Content rating
        if any(word in query_text for word in ["family", "kids"]):
            params["filter.content_rating"] = "TV-G,TV-PG"
        elif "mature" in query_text:
            params["filter.content_rating"] = "TV-MA"
            
        # Genre tags
        tv_tags = []
        if "drama" in query_text:
            tv_tags.append("urn:tag:genre:media:drama")
        if "comedy" in query_text:
            tv_tags.append("urn:tag:genre:media:comedy")
        if "reality" in query_text:
            tv_tags.append("urn:tag:genre:media:reality")
        if "documentary" in query_text:
            tv_tags.append("urn:tag:genre:media:documentary")
        if "crime" in query_text:
            tv_tags.append("urn:tag:genre:media:crime")
        if any(word in query_text for word in ["sci-fi", "science fiction"]):
            tv_tags.append("urn:tag:genre:media:science_fiction")
        if "fantasy" in query_text:
            tv_tags.append("urn:tag:genre:media:fantasy")
        if "anime" in query_text:
            tv_tags.append("urn:tag:genre:media:anime")
            
        if tv_tags:
            params["filter.tags"] = ",".join(tv_tags)
            
    # =============================================================================
    # BOOK ENTITY
    # =============================================================================
    elif any(word in query_text for word in ["book", "novel", "publication", "literature"]):
        entity_type = "urn:entity:book"
        params["filter.type"] = entity_type
        
        # Publication year filters
        year_match = re.search(r'(19|20)\d{2}', query_text)
        if year_match:
            year = year_match.group()
            params["filter.publication_year.min"] = year
            
        if any(word in query_text for word in ["recent", "new"]):
            params["filter.publication_year.min"] = "2020"
            
    # =============================================================================
    # PLACE ENTITY (DEFAULT) - Simplified and fixed
    # =============================================================================
    else:
        entity_type = "urn:entity:place"
        params["filter.type"] = entity_type
        
        # Basic place tags
        place_tags = []
        
        if any(word in query_text for word in ["restaurant", "food", "dining", "eat"]):
            place_tags.append("urn:tag:genre:place:restaurant")
        elif any(word in query_text for word in ["bar", "pub", "nightlife", "drinks"]):
            place_tags.append("urn:tag:genre:place:bar")
        elif any(word in query_text for word in ["hotel", "accommodation", "stay"]):
            place_tags.append("urn:tag:genre:place:hotel")
        elif any(word in query_text for word in ["museum", "theater", "entertainment"]):
            place_tags.append("urn:tag:genre:place:entertainment")
        elif any(word in query_text for word in ["shopping", "mall", "store"]):
            place_tags.append("urn:tag:genre:place:shopping")
        elif any(word in query_text for word in ["park", "outdoor", "nature"]):
            place_tags.append("urn:tag:genre:place:park")
            
        if place_tags:
            params["filter.tags"] = ",".join(place_tags)
            
        # Basic popularity filter
        if any(word in query_text for word in ["popular", "trending"]):
            params["filter.popularity.min"] = "0.7"
    
    return entity_type, params


def validate_parameters_for_entity(entity_type: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and filter parameters based on entity type support"""
    
    # Define supported parameters for each entity type based on the documentation
    supported_params = {
        "urn:entity:artist": {
            "filter.type", "bias.trends", "filter.exclude.entities", "filter.external.exists",
            "filter.parents.types", "filter.popularity.min", "filter.popularity.max", "filter.exclude.tags",
            "operator.exclude.tags", "filter.external.exists", "operator.filter.external.exists",
            "filter.results.entities", "filter.results.entities.query", "filter.tags", "operator.filter.tags",
            "offset", "signal.demographics.age", "signal.demographics.audiences", 
            "signal.demographics.audiences.weight", "signal.demographics.gender", "signal.interests.entities",
            "signal.interests.tags", "take"
        },
        "urn:entity:book": {
            "filter.type", "bias.trends", "filter.exclude.entities", "filter.exclude.tags",
            "operator.exclude.tags", "filter.external.exists", "operator.filter.external.exists",
            "filter.parents.types", "filter.popularity.min", "filter.popularity.max",
            "filter.publication_year.min", "filter.publication_year.max", "filter.results.entities",
            "filter.results.entities.query", "filter.tags", "operator.filter.tags", "offset",
            "signal.demographics.audiences", "signal.demographics.age", "signal.demographics.audiences.weight",
            "signal.demographics.gender", "signal.interests.entities", "signal.interests.tags", "take"
        },
        "urn:entity:brand": {
            "filter.type", "bias.trends", "filter.exclude.entities", "filter.exclude.tags",
            "operator.exclude.tags", "filter.external.exists", "operator.filter.external.exists",
            "filter.parents.types", "filter.popularity.min", "filter.popularity.max",
            "filter.results.entities", "filter.results.entities.query", "filter.tags", "operator.filter.tags", 
            "offset", "signal.demographics.audiences", "signal.demographics.age", "signal.demographics.audiences.weight",
            "signal.demographics.gender", "signal.interests.entities", "signal.interests.tags", "take"
        },
        "urn:entity:destination": {
            "filter.type", "bias.trends", "filter.exclude.entities", "filter.exclude.tags", 
            "operator.exclude.tags", "filter.external.exists", "operator.filter.external.exists",
            "filter.geocode.name", "filter.geocode.admin1_region", "filter.geocode.admin2_region", "filter.geocode.country_code", 
            "filter.location", "filter.location.geohash", "filter.exclude.location.geohash", "filter.location.radius",
            "filter.parents.types", "filter.popularity.min", "filter.popularity.max",
            "filter.results.entities", "filter.results.entities.query", "filter.tags", "operator.filter.tags",
            "offset", "signal.demographics.age", "signal.demographics.audiences",
            "signal.demographics.audiences.weight",
            "signal.demographics.gender", "signal.interests.entities", "signal.interests.tags", "take"
        },
        "urn:entity:movie": {
            "filter.type", "bias.trends", "filter.content_rating", "filter.exclude.entities",
            "filter.external.exists", "operator.filter.external.exists", "filter.exclude.tags",
            "operator.exclude.tags", "filter.parents.types", "filter.popularity.min", "filter.popularity.max",
            "filter.release_year.min", "filter.release_year.max", "filter.release_country",
            "operator.filter.release_country", "filter.rating.min", "filter.rating.max",
            "filter.results.entities", "filter.results.entities.query", "filter.tags", "operator.filter.tags",
            "offset", "signal.demographics.audiences", "signal.demographics.age", 
            "signal.demographics.audiences.weight", "signal.demographics.gender", "signal.interests.entities",
            "signal.interests.tags", "take"
        },
        "urn:entity:person": {
            "filter.type", "bias.trends", "filter.exclude.entities", "filter.external.exists",
            "operator.filter.external.exists", "filter.exclude.tags", "operator.exclude.tags",
            "filter.gender", "filter.parents.types", "filter.popularity.max", "filter.popularity.min",
            "filter.results.entities", "filter.results.entities.query", "filter.tags", "operator.filter.tags",
            "offset", "signal.demographics.age", "signal.demographics.audiences", 
            "signal.demographics.audiences.weight", "signal.demographics.gender", "signal.interests.entities",
            "signal.interests.tags", "take", "filter.date_of_birth.min", "filter.date_of_birth.max",
            "filter.date_of_death.min", "filter.date_of_death.max"
        },
        "urn:entity:place": {
            "filter.type", "bias.trends", "filter.address", "filter.exclude.entities", "filter.exclude.tags", 
            "operator.exclude.tags", "filter.external.exists", "operator.filter.external.exists", "filter.external.tripadvisor.rating.count.max",
            "filter.external.tripadvisor.rating.count.min", "filter.external.tripadvisor.rating.max", "filter.external.tripadvisor.rating.min",
            "filter.geocode.name", "filter.geocode.admin1_region", "filter.geocode.admin2_region", "filter.geocode.country_code", "filter.hotel_class.max",
            "filter.hotel_class.min", "filter.hours", "filter.location", "filter.location.geohash", "filter.exclude.location.geohash", "filter.location.radius",
            "filter.parents.types", "filter.popularity.min", "filter.popularity.max", "filter.price_level.max", "filter.price_level.min",
            "filter.price_range.from", "filter.price_range.to", "filter.properties.business_rating.min", "filter.properties.business_rating.max", "filter.properties.resy.rating.min",
            "filter.properties.resy.rating.max", "filter.references_brand", "filter.results.entities", "filter.results.entities.query", "filter.resy.rating_count.min", "filter.resy.rating_count.max",
            "filter.resy.rating.party.min", "filter.resy.rating.party.max", "filter.tags", "operator.filter.tags", "offset", "signal.demographics.age", "signal.demographics.audiences", "signal.demographics.audiences.weight",
            "signal.demographics.gender", "signal.interests.entities", "signal.interests.tags", "take"
        },
        "urn:entity:podcast": {
            "filter.type", "bias.trends", "filter.exclude.entities", "filter.exclude.tags",
            "operator.exclude.tags", "filter.external.exists", "operator.filter.external.exists",
            "filter.parents.types", "filter.popularity.min", "filter.popularity.max",
            "filter.results.entities", "filter.results.entities.query", "filter.tags", "operator.filter.tags", 
            "offset", "signal.demographics.audiences", "signal.demographics.age", "signal.demographics.audiences.weight",
            "signal.demographics.gender", "signal.interests.entities", "signal.interests.tags", "take"
        },
        "urn:entity:tv_show": {
            "filter.type", "bias.trends", "filter.content_rating", "filter.exclude.entities",
            "filter.external.exists", "operator.filter.external.exists", "filter.exclude.tags",
            "operator.exclude.tags", "filter.finale_year.max", "filter.finale_year.min",
            "filter.latest_known_year.max", "filter.latest_known_year.min", "filter.parents.types",
            "filter.popularity.max", "filter.popularity.min", "filter.release_year.max",
            "filter.release_year.min", "filter.release_country", "operator.filter.release_country",
            "filter.rating.max", "filter.rating.min", "filter.results.entities",
            "filter.results.entities.query", "filter.tags", "operator.filter.tags", "offset",
            "signal.demographics.age", "signal.demographics.audiences", "signal.demographics.audiences.weight",
            "signal.demographics.gender", "signal.interests.entities", "signal.interests.tags", "take"
        },
        "urn:entity:video_game": {
            "filter.type", "bias.trends", "filter.exclude.entities", "filter.exclude.tags",
            "operator.exclude.tags", "filter.external.exists", "operator.filter.external.exists",
            "filter.parents.types", "filter.popularity.min", "filter.popularity.max",
            "filter.results.entities", "filter.results.entities.query", "filter.tags", "operator.filter.tags", 
            "offset", "signal.demographics.audiences", "signal.demographics.age", "signal.demographics.audiences.weight",
            "signal.demographics.gender", "signal.interests.entities", "signal.interests.tags", "take"
        }
        
    }
    
    # Get supported parameters for this entity type
    if entity_type in supported_params:
        allowed_params = supported_params[entity_type]
        # Filter out unsupported parameters
        filtered_params = {k: v for k, v in params.items() if k in allowed_params}
        return filtered_params
    
    # If entity type not recognized, return original params
    return params

def _get_demographic_signals(social_context: str) -> Dict[str, str]:
    """Get demographic signals based on social context"""
    signals = {}
    
    # Age group mappings for different social contexts
    context_age_map = {
        "friends": "25_to_29,30_to_34",
        "couple": "25_to_29,30_to_34,35_to_44", 
        "family": "30_to_34,35_to_44",
        "business": "35_to_44,45_to_54",
        "solo": "25_to_29,30_to_34",
        "large_group": "25_to_29,30_to_34",
        "tourists": "25_to_29,30_to_34,35_to_44",
        "locals": "30_to_34,35_to_44"
    }
    
    if social_context in context_age_map:
        signals["signal.demographics.age"] = context_age_map[social_context]
    
    return signals

async def make_qloo_request(endpoint: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
    """Make a request to the QLOO API with proper error handling."""
    qloo_api_key = os.getenv("QLOO_API_KEY")
    if not qloo_api_key:
        return {"error": "QLOO_API_KEY environment variable not set"}
    
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
        "x-api-key": qloo_api_key  # Updated header name
    }
    
    async with httpx.AsyncClient() as client:
        try:
            if params:
                # Build query string
                query_string = "&".join([f"{k}={v}" for k, v in params.items() if v])
                full_url = f"{endpoint}?{query_string}" if query_string else endpoint
            else:
                full_url = endpoint
                
            print(f"🌐 Making request to: {full_url}")
            
            response = await client.get(full_url, headers=headers, timeout=30.0)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {"error": f"API request failed: {str(e)}"}

# =============================================================================
# COMPREHENSIVE ENTITY TYPE EXAMPLES AND USAGE
# =============================================================================

"""
EXAMPLE QUERIES SUPPORTED BY THE COMPREHENSIVE PARAMETER SYSTEM:

PLACE QUERIES:
• "Find expensive Japanese restaurants open on Sunday in Tokyo"
  → urn:entity:place + restaurant tag + Japanese cuisine + price_level.min=3 + hours=Sunday + location

• "Budget hotels with 4+ star rating near Times Square"  
  → urn:entity:place + hotel tag + hotel_class.min=4 + price_level.max=2 + address filter

• "Popular bars with good ratings in downtown"
  → urn:entity:place + bar tag + popularity.min=0.7 + business_rating.min=3.5

• "Family-friendly restaurants with reservations for 6 people"
  → urn:entity:place + restaurant tag + resy filters + party_size=6

MOVIE QUERIES:
• "Popular action movies from 2020-2023 rated R"
  → urn:entity:movie + action tag + release_year filters + content_rating=R

• "Classic family-friendly comedies"
  → urn:entity:movie + comedy tag + content_rating=G,PG + release_year.max=1990

TV SHOW QUERIES:
• "Recent Netflix series that ended in 2023"
  → urn:entity:tv_show + release_year.min=2020 + finale_year.max=2023

BOOK QUERIES:
• "Bestselling novels published after 2020"
  → urn:entity:book + publication_year.min=2020 + popularity.min=0.7

ARTIST QUERIES:
• "Trending musicians with high popularity"
  → urn:entity:artist + bias.trends=high + popularity.min=0.7

BRAND QUERIES:
• "Popular retail chains"
  → urn:entity:brand + popularity.min=0.7

And many more combinations...
"""

# =============================================================================
# MAIN MCP TOOLS WITH COMPREHENSIVE ENTITY SUPPORT
# =============================================================================

@mcp.tool()
async def get_qloo_recommendations(query: str, social_context: str = "friends") -> str:
    """Get personalized recommendations using Qloo's Insights API with comprehensive parameter extraction.
    
    Supports ALL 10 entity types with their COMPLETE parameter sets:
    
    🎨 ARTISTS: Musicians, painters, performers
       • Genre tags (rock, jazz, classical), popularity, trends, external platforms
       • Example: "Find trending indie rock musicians with high popularity on Spotify"
    
    📚 BOOKS: Novels, publications 
       • Genre tags, publication years, popularity, external platforms (Goodreads)
       • Example: "Recent bestselling sci-fi novels published after 2020"
    
    🏢 BRANDS: Retail chains, companies
       • Category tags (fashion, tech, luxury), popularity, trends, subsidiaries
       • Example: "Trending sustainable tech brands with social media presence"
    
    🗺️ DESTINATIONS: Cities, neighborhoods
       • Geographic filters (country, state, city), popularity, destination types
       • Example: "Popular tourist destinations in California with beach access"
    
    🎬 MOVIES: Films with comprehensive filtering
       • Genre, year, rating, country, popularity, external platforms (IMDb)
       • Example: "Highly rated indie comedies from 2020-2023 on IMDb"
    
    👤 PEOPLE: Celebrities, public figures
       • Gender, birth/death dates, profession tags, popularity, social platforms
       • Example: "Famous female directors born after 1970 trending on Instagram"
    
    🏢 PLACES: Restaurants, hotels, venues (MOST COMPREHENSIVE)
       • Price levels, ratings, hours, hotel classes, party sizes, cuisines, locations
       • Example: "Expensive Japanese restaurants open Sunday with reservations for 6"
    
    🎙️ PODCASTS: Audio series
       • Category tags (comedy, tech, crime), popularity, trends
       • Example: "Top trending true crime podcasts"
    
    📺 TV SHOWS: Series with detailed filtering
       • Genre, years, finale dates, countries, ratings, content ratings
       • Example: "Recent Korean dramas that ended in 2023 with high ratings"
    
    🎮 VIDEO GAMES: Gaming content
       • Genre tags (RPG, action), platform tags (PC, console), popularity
       • Example: "Trending indie RPG games on PC with high ratings"

    Args:
        query: Natural language query with rich parameter extraction
        social_context: Social situation (solo, couple, family, friends, business, large_group, tourists, locals)
    """
    
    try:
        context_enum = SocialContext(social_context.lower())
    except ValueError:
        valid_contexts = [c.value for c in SocialContext]
        return f"Invalid social context '{social_context}'. Valid options: {', '.join(valid_contexts)}"
    
    print(f"🔍 Processing query: {query}")
    print(f"👥 Social context: {social_context}")
    
    try:
        # Classify the query and determine Qloo use case
        use_case, params = classify_user_query(query)
        print(f"🎯 Detected Qloo use case: {use_case.value}")
        
        # Build appropriate Qloo API parameters
        qloo_params = build_qloo_parameters(use_case, params, social_context)
        print(f"📋 Qloo parameters: {qloo_params}")
        
        # Make the API request to insights endpoint
        endpoint = f"{QLOO_API_BASE}/insights"
        response = await make_qloo_request(endpoint, qloo_params)
        
        if "error" in response:
            return f"❌ Error: {response['error']}"
        
        # Format response based on use case
        return _format_qloo_response(response, use_case, params, social_context)
            
    except Exception as e:
        return f"❌ Error processing query: {str(e)}"

@mcp.tool()
async def get_demographic_insights(entity_or_tag: str, location: str = "") -> str:
    """Get demographic insights for a specific entity or tag using Qloo's Demographics API.

    Args:
        entity_or_tag: Entity name or tag to analyze (e.g. "action movies", "sushi restaurants")
        location: Optional location filter
    """
    
    print(f"📊 Getting demographic insights for: {entity_or_tag}")
    
    try:
        # Build demographic insights parameters
        qloo_params = {
            "filter.type": "urn:demographics"
        }
        
        # Determine if it's a tag or entity
        if any(word in entity_or_tag.lower() for word in ["movie", "film", "action", "comedy", "drama"]):
            # Media tags
            if "action" in entity_or_tag.lower():
                qloo_params["signal.interests.tags"] = "urn:tag:genre:media:action"
            elif "comedy" in entity_or_tag.lower():
                qloo_params["signal.interests.tags"] = "urn:tag:genre:media:comedy"
            elif "drama" in entity_or_tag.lower():
                qloo_params["signal.interests.tags"] = "urn:tag:genre:media:drama"
        elif any(word in entity_or_tag.lower() for word in ["restaurant", "food", "cuisine"]):
            # Food/restaurant related
            qloo_params["signal.interests.tags"] = "urn:tag:genre:place:restaurant"
        
        if location:
            qloo_params["signal.location.query"] = location
        
        endpoint = f"{QLOO_API_BASE}/insights"
        response = await make_qloo_request(endpoint, qloo_params)
        
        if "error" in response:
            return f"❌ Error: {response['error']}"
        
        return _format_demographic_response(response, entity_or_tag)
        
    except Exception as e:
        return f"❌ Error getting demographic insights: {str(e)}"

@mcp.tool()
async def get_location_heatmap(location: str, interest_type: str = "restaurants") -> str:
    """Generate geographic heatmap data for a location using Qloo's Heatmaps API.

    Args:
        location: Location to analyze (e.g. "NYC", "Lower East Side")
        interest_type: Type of interest to map (restaurants, entertainment, etc.)
    """
    
    print(f"🗺️ Generating heatmap for: {location} - {interest_type}")
    
    try:
        # Build heatmap parameters
        qloo_params = {
            "filter.type": "urn:heatmap",
            "filter.location.query": location
        }
        
        # Add interest signals based on type
        if "restaurant" in interest_type.lower():
            qloo_params["signal.interests.tags"] = "urn:tag:genre:place:restaurant"
        elif "entertainment" in interest_type.lower():
            qloo_params["signal.interests.tags"] = "urn:tag:genre:place:entertainment"
        elif "bar" in interest_type.lower() or "nightlife" in interest_type.lower():
            qloo_params["signal.interests.tags"] = "urn:tag:genre:place:bar"
        
        endpoint = f"{QLOO_API_BASE}/insights"
        response = await make_qloo_request(endpoint, qloo_params)
        
        if "error" in response:
            return f"❌ Error: {response['error']}"
        
        return _format_heatmap_response(response, location, interest_type)
        
    except Exception as e:
        return f"❌ Error generating heatmap: {str(e)}"

@mcp.tool()
async def debug_query_analysis(query: str) -> str:
    """Debug tool to show how a query gets analyzed and what parameters are extracted.

    Args:
        query: Natural language query to analyze
    """
    
    print(f"🔍 Analyzing query: {query}")
    
    try:
        # Classify the query
        use_case, params = classify_user_query(query)
        print(f"🎯 Detected use case: {use_case.value}")
        
        # Get entity and parameters
        query_text = params.get("query_lower", "")
        entity_type, entity_params = _determine_entity_and_comprehensive_params(query_text)
        
        # Build Qloo parameters
        qloo_params = build_qloo_parameters(use_case, params, "friends")
        
        # Format debug output
        output = f"🔬 **Query Analysis Debug**\n\n"
        output += f"**Original Query:** {query}\n\n"
        output += f"**Detected Use Case:** {use_case.value}\n\n"
        output += f"**Entity Type:** {entity_type}\n\n"
        output += f"**Extracted Parameters:**\n"
        
        for key, value in entity_params.items():
            output += f"  • {key}: {value}\n"
            
        output += f"\n**Final Qloo API Parameters:**\n"
        for key, value in qloo_params.items():
            output += f"  • {key}: {value}\n"
            
        return output
        
    except Exception as e:
        return f"❌ Error analyzing query: {str(e)}"

@mcp.tool()
async def analyze_taste_profile(query: str, location: str = "") -> str:
    """Analyze taste profile and get tag metadata using Qloo's Taste Analysis API.

    Args:
        query: What to analyze (e.g. "Italian restaurant characteristics", "action movie tags")
        location: Optional location filter
    """
    
    print(f"🏷️ Analyzing taste profile: {query}")
    
    try:
        # Build taste analysis parameters
        qloo_params = {
            "filter.type": "urn:tag"
        }
        
        # Determine tag types and parent types
        if any(word in query.lower() for word in ["movie", "film", "media"]):
            qloo_params["filter.tag.types"] = "urn:tag:keyword:media"
            qloo_params["filter.parents.types"] = "urn:entity:movie,urn:entity:tv_show"
        elif any(word in query.lower() for word in ["restaurant", "place", "venue"]):
            qloo_params["filter.tag.types"] = "urn:tag:genre:place"
            qloo_params["filter.parents.types"] = "urn:entity:place"
        
        if location:
            qloo_params["signal.location.query"] = location
        
        endpoint = f"{QLOO_API_BASE}/insights"
        response = await make_qloo_request(endpoint, qloo_params)
        
        if "error" in response:
            return f"❌ Error: {response['error']}"
        
        return _format_taste_analysis_response(response, query)
        
    except Exception as e:
        return f"❌ Error analyzing taste profile: {str(e)}"

# =============================================================================
# RESPONSE FORMATTING FUNCTIONS
# =============================================================================

def _format_qloo_response(response: Dict[str, Any], use_case: QlooUseCase, 
                         params: Dict[str, Any], social_context: str) -> str:
    """Format Qloo API response based on use case"""
    
    if use_case == QlooUseCase.RECOMMENDATION_INSIGHTS:
        return _format_recommendation_response(response, params, social_context)
    elif use_case == QlooUseCase.DEMOGRAPHIC_INSIGHTS:
        return _format_demographic_response(response, params.get("query", ""))
    elif use_case == QlooUseCase.HEATMAPS:
        return _format_heatmap_response(response, params.get("location", ""), "general")
    elif use_case == QlooUseCase.LOCATION_BASED_INSIGHTS:
        return _format_location_based_response(response, params, social_context)
    elif use_case == QlooUseCase.TASTE_ANALYSIS:
        return _format_taste_analysis_response(response, params.get("query", ""))
    else:
        return _format_generic_response(response)

def _format_recommendation_response(response: Dict[str, Any], 
                                  params: Dict[str, Any], social_context: str) -> str:
    """Format recommendation insights response for all entity types"""
    
    results = response.get('results', {})
    entities = results.get('entities', [])
    
    if not entities:
        location = params.get("location", "")
        return f"🔍 No recommendations found for your query in {location}. Try different search terms."
    
    location = params.get("location", "")
    output = f"🎯 **Recommendations for {social_context} in {location}**\n\n"
    
    for i, entity in enumerate(entities[:5], 1):
        name = entity.get('name', 'Unknown')
        entity_type = entity.get('subtype', '').replace('urn:entity:', '')
        popularity = entity.get('popularity', 0)
        
        # Extract properties
        properties = entity.get('properties', {})
        
        output += f"{i}. **{name}**\n"
        
        # Entity-specific formatting
        if entity_type == "place":
            address = properties.get('address', '')
            if address:
                output += f"   📍 {address}\n"
                
            # Price level
            price_level = properties.get('price_level')
            if price_level:
                price_emoji = "💰" * int(price_level)
                output += f"   {price_emoji} Price Level: {price_level}\n"
                
            # Business rating
            business_rating = properties.get('business_rating')
            if business_rating:
                output += f"   ⭐ Rating: {business_rating}/5.0\n"
                
            # Hotel class
            hotel_class = properties.get('hotel_class')
            if hotel_class:
                output += f"   🏨 Hotel Class: {hotel_class} stars\n"
                
        elif entity_type == "movie":
            release_year = properties.get('release_year')
            if release_year:
                output += f"   📅 Released: {release_year}\n"
                
            content_rating = properties.get('content_rating')
            if content_rating:
                output += f"   🔞 Rating: {content_rating}\n"
                
            duration = properties.get('duration')
            if duration:
                output += f"   ⏱️ Duration: {duration} minutes\n"
                
        elif entity_type == "book":
            publication_year = properties.get('publication_year')
            if publication_year:
                output += f"   📚 Published: {publication_year}\n"
                
        elif entity_type == "tv_show":
            release_year = properties.get('release_year')
            finale_year = properties.get('finale_year')
            if release_year:
                year_range = f"{release_year}"
                if finale_year and finale_year != release_year:
                    year_range += f"-{finale_year}"
                output += f"   📺 Years: {year_range}\n"
                
        # Description (if available and short)
        description = properties.get('description', '')
        if description and len(description) < 150:
            output += f"   📝 {description}\n"
        
        # Show popularity score
        popularity_emoji = "🔥" if popularity > 0.8 else "⭐" if popularity > 0.5 else "📍"
        output += f"   {popularity_emoji} Popularity: {popularity:.2f}\n"
        
        # Extract and show tags
        tags = entity.get('tags', [])[:3]  # Show first 3 tags
        if tags:
            tag_names = []
            for tag in tags:
                tag_name = tag.get('name', '')
                if tag_name and len(tag_name) < 30:  # Skip very long tag names
                    tag_names.append(tag_name)
            if tag_names:
                output += f"   🏷️ {', '.join(tag_names)}\n"
        
        output += "\n"
    
    # Add social context advice
    context_advice = _get_context_advice(social_context)
    if context_advice:
        output += f"💡 **For {social_context}:** {context_advice}\n"
    
    return output

def _format_demographic_response(response: Dict[str, Any], entity_or_tag: str) -> str:
    """Format demographic insights response"""
    
    results = response.get('results', {})
    demographics = results.get('demographics', [])
    
    if not demographics:
        return f"📊 No demographic data found for '{entity_or_tag}'"
    
    output = f"📊 **Demographic Analysis: {entity_or_tag}**\n\n"
    
    for demo in demographics:
        entity_id = demo.get('entity_id', 'Unknown')
        query_data = demo.get('query', {})
        
        # Age demographics
        age_data = query_data.get('age', {})
        if age_data:
            output += "🎂 **Age Demographics:**\n"
            for age_group, score in age_data.items():
                emoji = "🔥" if score > 0.3 else "📈" if score > 0 else "📉"
                formatted_age = age_group.replace('_', ' ').title()
                output += f"   {emoji} {formatted_age}: {score:.2f}\n"
            output += "\n"
        
        # Gender demographics
        gender_data = query_data.get('gender', {})
        if gender_data:
            output += "👥 **Gender Demographics:**\n"
            for gender, score in gender_data.items():
                emoji = "📈" if score > 0 else "📉"
                output += f"   {emoji} {gender.title()}: {score:.2f}\n"
            output += "\n"
    
    return output

def _format_heatmap_response(response: Dict[str, Any], location: str, interest_type: str) -> str:
    """Format heatmap response"""
    
    results = response.get('results', {})
    heatmap_data = results.get('heatmap', [])
    
    if not heatmap_data:
        return f"🗺️ No heatmap data found for {location}"
    
    output = f"🗺️ **Heatmap Analysis: {interest_type} in {location}**\n\n"
    
    # Show top 5 hotspots
    sorted_data = sorted(heatmap_data, key=lambda x: x.get('query', {}).get('affinity', 0), reverse=True)
    
    output += "🔥 **Top Hotspots:**\n"
    for i, point in enumerate(sorted_data[:5], 1):
        location_data = point.get('location', {})
        query_data = point.get('query', {})
        
        lat = location_data.get('latitude', 0)
        lng = location_data.get('longitude', 0)
        affinity = query_data.get('affinity', 0)
        popularity = query_data.get('popularity', 0)
        
        output += f"{i}. **Location ({lat:.4f}, {lng:.4f})**\n"
        output += f"   🎯 Affinity: {affinity:.3f}\n"
        output += f"   ⭐ Popularity: {popularity:.3f}\n\n"
    
    # Summary stats
    total_points = len(heatmap_data)
    avg_affinity = sum(point.get('query', {}).get('affinity', 0) for point in heatmap_data) / max(total_points, 1)
    
    output += f"📈 **Summary:**\n"
    output += f"   • Total data points: {total_points}\n"
    output += f"   • Average affinity: {avg_affinity:.3f}\n"
    
    return output

def _format_location_based_response(response: Dict[str, Any], 
                                  params: Dict[str, Any], social_context: str) -> str:
    """Format location-based insights response"""
    # Similar to recommendation response but with location context
    return _format_recommendation_response(response, params, social_context)

def _format_taste_analysis_response(response: Dict[str, Any], query: str) -> str:
    """Format taste analysis response"""
    
    results = response.get('results', {})
    tags = results.get('tags', [])
    
    if not tags:
        return f"🏷️ No taste analysis data found for '{query}'"
    
    output = f"🏷️ **Taste Analysis: {query}**\n\n"
    
    # Show top tags
    for i, tag in enumerate(tags[:10], 1):
        tag_name = tag.get('name', 'Unknown')
        tag_types = tag.get('types', [])
        subtype = tag.get('subtype', '')
        
        output += f"{i}. **{tag_name}**\n"
        output += f"   🔖 Type: {subtype.replace('urn:tag:', '').replace(':', ' › ')}\n"
        
        if tag_types:
            relevant_types = [t.replace('urn:entity:', '') for t in tag_types[:3]]
            output += f"   📂 Associated with: {', '.join(relevant_types)}\n"
        
        output += "\n"
    
    return output

def _format_generic_response(response: Dict[str, Any]) -> str:
    """Format generic response for unknown use cases"""
    
    if 'results' in response:
        results = response['results']
        if isinstance(results, dict):
            return f"📋 **Results:**\n{json.dumps(results, indent=2)[:500]}..."
        else:
            return f"📋 **Results:** {str(results)[:500]}..."
    else:
        return f"📋 **Response:** {json.dumps(response, indent=2)[:500]}..."

def _get_context_advice(social_context: str) -> str:
    """Get advice based on social context"""
    advice_map = {
        "friends": "Look for places with group seating and social atmosphere",
        "couple": "Consider intimate settings with romantic ambiance",
        "family": "Family-friendly places with diverse options",
        "business": "Professional atmosphere, good for conversations",
        "solo": "Places where solo dining/visiting is comfortable",
        "large_group": "Venues that can accommodate big parties",
        "tourists": "Popular attractions and must-see spots",
        "locals": "Hidden gems and authentic local experiences"
    }
    
    return advice_map.get(social_context, "")

# =============================================================================
# LEGACY CULTURAL ANALYSIS FUNCTIONS (for backward compatibility)
# =============================================================================

@mcp.tool()
async def analyze_cultural_moment(location: str, 
                                social_context: str = "friends", 
                                include_details: bool = True) -> str:
    """Analyze cultural context using Qloo's insights (wrapper for backward compatibility).

    Args:
        location: City name (e.g. Mumbai, New York, Tokyo)
        social_context: Social situation (solo, couple, family, friends, business, large_group, tourists, locals)
        include_details: Whether to include detailed cultural breakdown
    """
    
    # Use the new Qloo-based approach
    query = f"cultural analysis of {location}"
    return await get_qloo_recommendations(query, social_context)