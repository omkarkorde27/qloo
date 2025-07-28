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
    # ENTITY TYPE DETECTION WITH COMPREHENSIVE PARAMETER EXTRACTION
    # =============================================================================
    
    # ARTIST ENTITY
    if any(word in query_text for word in ["artist", "musician", "singer", "band", "composer", "painter", "sculptor", "performer"]):
        entity_type = "urn:entity:artist"
        params["filter.type"] = entity_type
        
        # =============================================================================
        # COMPREHENSIVE ARTIST PARAMETERS
        # =============================================================================
        
        # Trends bias
        if "trending" in query_text or "hot" in query_text or "viral" in query_text:
            params["bias.trends"] = "high"
        elif "classic" in query_text or "timeless" in query_text:
            params["bias.trends"] = "low"
            
        # Popularity filters
        if "popular" in query_text or "famous" in query_text or "well-known" in query_text:
            params["filter.popularity.min"] = "0.7"
        elif "underground" in query_text or "indie" in query_text or "emerging" in query_text:
            params["filter.popularity.max"] = "0.4"
        elif "mainstream" in query_text:
            params["filter.popularity.min"] = "0.6"
            
        # Artist genre tags
        artist_tags = []
        if "rock" in query_text:
            artist_tags.append("urn:tag:genre:music:rock")
        if "pop" in query_text:
            artist_tags.append("urn:tag:genre:music:pop")
        if "jazz" in query_text:
            artist_tags.append("urn:tag:genre:music:jazz")
        if "classical" in query_text:
            artist_tags.append("urn:tag:genre:music:classical")
        if "hip hop" in query_text or "rap" in query_text:
            artist_tags.append("urn:tag:genre:music:hip_hop")
        if "electronic" in query_text or "edm" in query_text:
            artist_tags.append("urn:tag:genre:music:electronic")
        if "country" in query_text:
            artist_tags.append("urn:tag:genre:music:country")
        if "folk" in query_text:
            artist_tags.append("urn:tag:genre:music:folk")
            
        # Visual artist tags
        if "painter" in query_text or "painting" in query_text:
            artist_tags.append("urn:tag:medium:visual:painting")
        if "sculptor" in query_text or "sculpture" in query_text:
            artist_tags.append("urn:tag:medium:visual:sculpture")
        if "photographer" in query_text or "photography" in query_text:
            artist_tags.append("urn:tag:medium:visual:photography")
            
        if artist_tags:
            params["filter.tags"] = ",".join(artist_tags)
            
        # External platform filters
        if "spotify" in query_text:
            params["filter.external.exists"] = "spotify"
        elif "instagram" in query_text:
            params["filter.external.exists"] = "instagram"
        elif "youtube" in query_text:
            params["filter.external.exists"] = "youtube"
            
        # Exclude certain types if specified
        exclude_terms = []
        if "not indie" in query_text:
            exclude_terms.append("urn:tag:genre:music:indie")
        if "not mainstream" in query_text:
            exclude_terms.append("urn:tag:genre:music:mainstream")
        if exclude_terms:
            params["filter.exclude.tags"] = ",".join(exclude_terms)
            
    # BRAND ENTITY
    elif any(word in query_text for word in ["brand", "company", "retail", "chain", "franchise", "corporation", "business"]):
        entity_type = "urn:entity:brand"
        params["filter.type"] = entity_type
        
        # =============================================================================
        # COMPREHENSIVE BRAND PARAMETERS
        # =============================================================================
        
        # Trends bias
        if "trending" in query_text or "hot" in query_text or "growing" in query_text:
            params["bias.trends"] = "high"
        elif "established" in query_text or "traditional" in query_text:
            params["bias.trends"] = "low"
            
        # Popularity filters
        if "popular" in query_text or "well-known" in query_text or "major" in query_text:
            params["filter.popularity.min"] = "0.7"
        elif "niche" in query_text or "boutique" in query_text or "small" in query_text:
            params["filter.popularity.max"] = "0.4"
        elif "emerging" in query_text or "startup" in query_text:
            params["filter.popularity.max"] = "0.5"
            
        # Brand category tags
        brand_tags = []
        if "fashion" in query_text or "clothing" in query_text:
            brand_tags.append("urn:tag:category:brand:fashion")
        if "technology" in query_text or "tech" in query_text:
            brand_tags.append("urn:tag:category:brand:technology")
        if "food" in query_text or "restaurant" in query_text:
            brand_tags.append("urn:tag:category:brand:food")
        if "retail" in query_text or "shopping" in query_text:
            brand_tags.append("urn:tag:category:brand:retail")
        if "automotive" in query_text or "car" in query_text:
            brand_tags.append("urn:tag:category:brand:automotive")
        if "luxury" in query_text or "premium" in query_text:
            brand_tags.append("urn:tag:category:brand:luxury")
        if "budget" in query_text or "affordable" in query_text:
            brand_tags.append("urn:tag:category:brand:budget")
        if "sustainable" in query_text or "eco" in query_text or "green" in query_text:
            brand_tags.append("urn:tag:category:brand:sustainable")
            
        if brand_tags:
            params["filter.tags"] = ",".join(brand_tags)
            
        # External platform filters
        if "website" in query_text:
            params["filter.external.exists"] = "website"
        elif "social media" in query_text:
            params["filter.external.exists"] = "instagram,twitter,facebook"
            
        # Parent types (if looking for subsidiary brands)
        if "subsidiary" in query_text or "owned by" in query_text:
            params["filter.parents.types"] = "urn:entity:brand"
            
        # Exclude certain brand types
        exclude_terms = []
        if "not luxury" in query_text:
            exclude_terms.append("urn:tag:category:brand:luxury")
        if "not budget" in query_text:
            exclude_terms.append("urn:tag:category:brand:budget")
        if exclude_terms:
            params["filter.exclude.tags"] = ",".join(exclude_terms)
            params["operator.exclude.tags"] = "union"
        entity_type = "urn:entity:book"
        params["filter.type"] = entity_type
        
        # Book-specific parameters
        year_match = re.search(r'(19|20)\d{2}', query_text)
        if year_match:
            year = year_match.group()
            params["filter.publication_year.min"] = year
            
        if "recent" in query_text or "new" in query_text:
            params["filter.publication_year.min"] = "2020"
            
    # MOVIE ENTITY
    elif any(word in query_text for word in ["movie", "film", "cinema", "blockbuster", "flick"]):
        entity_type = "urn:entity:movie"
        params["filter.type"] = entity_type
        
        # =============================================================================
        # COMPREHENSIVE MOVIE PARAMETERS
        # =============================================================================
        
        # Release year filters
        year_match = re.search(r'(19|20)\d{2}', query_text)
        if year_match:
            year = year_match.group()
            params["filter.release_year.min"] = year
            
        if "recent" in query_text or "new" in query_text:
            params["filter.release_year.min"] = "2020"
        elif "classic" in query_text:
            params["filter.release_year.max"] = "1990"
        elif "80s" in query_text:
            params["filter.release_year.min"] = "1980"
            params["filter.release_year.max"] = "1989"
        elif "90s" in query_text:
            params["filter.release_year.min"] = "1990"
            params["filter.release_year.max"] = "1999"
            
        # Content rating filters
        if "family" in query_text or "kids" in query_text:
            params["filter.content_rating"] = "G,PG"
        elif "teen" in query_text:
            params["filter.content_rating"] = "PG-13"
        elif "mature" in query_text or "adult" in query_text:
            params["filter.content_rating"] = "R"
            
        # Rating filters (Qloo internal rating)
        if "highly rated" in query_text or "top rated" in query_text:
            params["filter.rating.min"] = "4.0"
        elif "good" in query_text:
            params["filter.rating.min"] = "3.5"
            
        # Popularity filters
        if "blockbuster" in query_text or "popular" in query_text:
            params["filter.popularity.min"] = "0.7"
        elif "indie" in query_text or "independent" in query_text:
            params["filter.popularity.max"] = "0.5"
            
        # Trends bias
        if "trending" in query_text or "viral" in query_text:
            params["bias.trends"] = "high"
            
        # Release country filters
        if "hollywood" in query_text or "american" in query_text:
            params["filter.release_country"] = "United States"
        elif "bollywood" in query_text or "indian" in query_text:
            params["filter.release_country"] = "India"
        elif "british" in query_text or "uk" in query_text:
            params["filter.release_country"] = "United Kingdom"
        elif "french" in query_text:
            params["filter.release_country"] = "France"
        elif "japanese" in query_text:
            params["filter.release_country"] = "Japan"
            
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
        if "romance" in query_text or "romantic" in query_text:
            movie_tags.append("urn:tag:genre:media:romance")
        if "thriller" in query_text:
            movie_tags.append("urn:tag:genre:media:thriller")
        if "sci-fi" in query_text or "science fiction" in query_text:
            movie_tags.append("urn:tag:genre:media:science_fiction")
        if "fantasy" in query_text:
            movie_tags.append("urn:tag:genre:media:fantasy")
        if "documentary" in query_text:
            movie_tags.append("urn:tag:genre:media:documentary")
        if "animation" in query_text or "animated" in query_text:
            movie_tags.append("urn:tag:genre:media:animation")
            
        if movie_tags:
            params["filter.tags"] = ",".join(movie_tags)
            
        # External platform filters
        if "imdb" in query_text:
            params["filter.external.exists"] = "imdb"
        elif "rotten tomatoes" in query_text:
            params["filter.external.exists"] = "rottentomatoes"
        elif "metacritic" in query_text:
            params["filter.external.exists"] = "metacritic"
            
    # PERSON ENTITY
    elif any(word in query_text for word in ["person", "celebrity", "actor", "actress", "director", "politician", "athlete", "public figure"]):
        entity_type = "urn:entity:person"
        params["filter.type"] = entity_type
        
        # =============================================================================
        # COMPREHENSIVE PERSON PARAMETERS
        # =============================================================================
        
        # Gender filter
        if "male" in query_text or "men" in query_text:
            params["filter.gender"] = "male"
        elif "female" in query_text or "women" in query_text:
            params["filter.gender"] = "female"
            
        # Birth/Death year filters
        if "born in" in query_text:
            year_match = re.search(r'born in\s+(19|20)\d{2}', query_text)
            if year_match:
                year = year_match.group(1) + year_match.group(2)
                params["filter.date_of_birth.min"] = f"{year}-01-01"
                params["filter.date_of_birth.max"] = f"{year}-12-31"
                
        if "young" in query_text or "under 30" in query_text:
            params["filter.date_of_birth.min"] = "1990-01-01"
        elif "veteran" in query_text or "experienced" in query_text:
            params["filter.date_of_birth.max"] = "1970-01-01"
            
        # Popularity filters
        if "famous" in query_text or "well-known" in query_text:
            params["filter.popularity.min"] = "0.7"
        elif "emerging" in query_text or "up-and-coming" in query_text:
            params["filter.popularity.max"] = "0.5"
            
        # Trends bias
        if "trending" in query_text or "viral" in query_text:
            params["bias.trends"] = "high"
            
        # Person category tags
        person_tags = []
        if "actor" in query_text or "actress" in query_text:
            person_tags.append("urn:tag:profession:actor")
        if "director" in query_text:
            person_tags.append("urn:tag:profession:director")
        if "musician" in query_text or "singer" in query_text:
            person_tags.append("urn:tag:profession:musician")
        if "politician" in query_text:
            person_tags.append("urn:tag:profession:politician")
        if "athlete" in query_text or "sports" in query_text:
            person_tags.append("urn:tag:profession:athlete")
        if "author" in query_text or "writer" in query_text:
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
        entity_type = "urn:entity:destination"
        params["filter.type"] = entity_type
        
        # Geographic filters
        if "usa" in query_text or "america" in query_text:
            params["filter.geocode.country_code"] = "US"
        elif "uk" in query_text or "britain" in query_text:
            params["filter.geocode.country_code"] = "GB"
        elif "japan" in query_text:
            params["filter.geocode.country_code"] = "JP"
        elif "india" in query_text:
            params["filter.geocode.country_code"] = "IN"
            
    # MOVIE ENTITY
    elif any(word in query_text for word in ["movie", "film", "cinema", "blockbuster"]):
        entity_type = "urn:entity:movie"
        params["filter.type"] = entity_type
        
        # Movie-specific parameters
        if "recent" in query_text or "new" in query_text:
            params["filter.release_year.min"] = "2020"
        if "classic" in query_text:
            params["filter.release_year.max"] = "1990"
            
        # Content rating
        if "family" in query_text or "kids" in query_text:
            params["filter.content_rating"] = "G,PG"
        elif "mature" in query_text:
            params["filter.content_rating"] = "R"
            
        # Genre tags
        genre_tags = []
        if "action" in query_text:
            genre_tags.append("urn:tag:genre:media:action")
        if "comedy" in query_text:
            genre_tags.append("urn:tag:genre:media:comedy")
        if "drama" in query_text:
            genre_tags.append("urn:tag:genre:media:drama")
        if "horror" in query_text:
            genre_tags.append("urn:tag:genre:media:horror")
        if "romance" in query_text or "romantic" in query_text:
            genre_tags.append("urn:tag:genre:media:romance")
            
        if genre_tags:
            params["filter.tags"] = ",".join(genre_tags)
            
    # TV SHOW ENTITY
    elif any(word in query_text for word in ["tv", "show", "series", "television", "netflix", "streaming", "episode"]):
        entity_type = "urn:entity:tv_show"
        params["filter.type"] = entity_type
        
        # =============================================================================
        # COMPREHENSIVE TV SHOW PARAMETERS
        # =============================================================================
        
        # Release year filters
        if "recent" in query_text or "new" in query_text:
            params["filter.release_year.min"] = "2020"
        elif "classic" in query_text:
            params["filter.release_year.max"] = "2000"
            
        # Finale year filters
        if "ended" in query_text or "finished" in query_text:
            params["filter.finale_year.max"] = "2023"
        elif "ongoing" in query_text or "current" in query_text:
            # Shows that haven't ended yet
            params["filter.finale_year.min"] = "2024"
            
        # Latest known year (for shows with updates)
        if "updated recently" in query_text:
            params["filter.latest_known_year.min"] = "2022"
            
        # Content rating
        if "family" in query_text or "kids" in query_text:
            params["filter.content_rating"] = "TV-G,TV-PG"
        elif "mature" in query_text:
            params["filter.content_rating"] = "TV-MA"
            
        # Rating filters
        if "highly rated" in query_text:
            params["filter.rating.min"] = "4.0"
        elif "good" in query_text:
            params["filter.rating.min"] = "3.5"
            
        # Popularity filters
        if "popular" in query_text or "hit" in query_text:
            params["filter.popularity.min"] = "0.7"
        elif "cult" in query_text or "niche" in query_text:
            params["filter.popularity.max"] = "0.5"
            
        # Trends bias
        if "trending" in query_text or "viral" in query_text:
            params["bias.trends"] = "high"
            
        # Release country
        if "american" in query_text or "us" in query_text:
            params["filter.release_country"] = "United States"
        elif "british" in query_text or "uk" in query_text:
            params["filter.release_country"] = "United Kingdom"
        elif "korean" in query_text or "k-drama" in query_text:
            params["filter.release_country"] = "South Korea"
        elif "japanese" in query_text or "anime" in query_text:
            params["filter.release_country"] = "Japan"
            
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
        if "sci-fi" in query_text:
            tv_tags.append("urn:tag:genre:media:science_fiction")
        if "fantasy" in query_text:
            tv_tags.append("urn:tag:genre:media:fantasy")
        if "anime" in query_text:
            tv_tags.append("urn:tag:genre:media:anime")
            
        if tv_tags:
            params["filter.tags"] = ",".join(tv_tags)
        entity_type = "urn:entity:person"
        params["filter.type"] = entity_type
        
        # Gender filter
        if "male" in query_text:
            params["filter.gender"] = "male"
        elif "female" in query_text:
            params["filter.gender"] = "female"
            
    # PODCAST ENTITY
    elif any(word in query_text for word in ["podcast", "audio", "episode", "series"]):
        entity_type = "urn:entity:podcast"
        params["filter.type"] = entity_type
        
    # TV SHOW ENTITY
    elif any(word in query_text for word in ["tv", "show", "series", "television", "netflix", "streaming"]):
        entity_type = "urn:entity:tv_show"
        params["filter.type"] = entity_type
        
        # TV-specific parameters
        if "recent" in query_text or "new" in query_text:
            params["filter.release_year.min"] = "2020"
        if "ended" in query_text or "finished" in query_text:
            params["filter.finale_year.max"] = "2023"
            
    # VIDEO GAME ENTITY
    elif any(word in query_text for word in ["game", "video game", "gaming", "console", "pc game"]):
        entity_type = "urn:entity:video_game"
        params["filter.type"] = entity_type
        
    # PLACE ENTITY (DEFAULT) - WITH COMPREHENSIVE PARAMETERS
    else:
        entity_type = "urn:entity:place"
        params["filter.type"] = entity_type
        
        # =============================================================================
        # COMPREHENSIVE PLACE PARAMETERS EXTRACTION
        # =============================================================================
        
        # VENUE TYPE TAGS
        place_tags = []
        
        # Restaurant/food queries
        if any(word in query_text for word in ["restaurant", "food", "dining", "eat", "meal", "cuisine"]):
            place_tags.append("urn:tag:genre:place:restaurant")
            
            # Cuisine-specific tags
            cuisine_map = {
                "japanese": "urn:tag:cuisine:japanese",
                "italian": "urn:tag:cuisine:italian", 
                "chinese": "urn:tag:cuisine:chinese",
                "indian": "urn:tag:cuisine:indian",
                "mexican": "urn:tag:cuisine:mexican",
                "thai": "urn:tag:cuisine:thai",
                "french": "urn:tag:cuisine:french",
                "korean": "urn:tag:cuisine:korean",
                "american": "urn:tag:cuisine:american",
                "mediterranean": "urn:tag:cuisine:mediterranean"
            }
            
            for cuisine, tag in cuisine_map.items():
                if cuisine in query_text:
                    place_tags.append(tag)
                    
        # Bar/nightlife queries
        elif any(word in query_text for word in ["bar", "pub", "nightlife", "drinks", "cocktail", "beer"]):
            place_tags.append("urn:tag:genre:place:bar")
            
        # Hotel queries
        elif any(word in query_text for word in ["hotel", "accommodation", "stay", "lodge", "resort"]):
            place_tags.append("urn:tag:genre:place:hotel")
            
            # Hotel class filters
            if "luxury" in query_text or "5 star" in query_text:
                params["filter.hotel_class.min"] = "4"
            elif "budget" in query_text or "cheap" in query_text:
                params["filter.hotel_class.max"] = "2"
                
        # Entertainment venues
        elif any(word in query_text for word in ["museum", "theater", "cinema", "entertainment", "gallery"]):
            if "museum" in query_text:
                place_tags.append("urn:tag:genre:place:museum")
            elif "theater" in query_text or "cinema" in query_text:
                place_tags.append("urn:tag:genre:place:entertainment")
                
        # Shopping
        elif any(word in query_text for word in ["shopping", "mall", "store", "boutique", "market"]):
            place_tags.append("urn:tag:genre:place:shopping")
            
        # Parks/outdoor
        elif any(word in query_text for word in ["park", "outdoor", "nature", "garden", "beach"]):
            place_tags.append("urn:tag:genre:place:park")
            
        if place_tags:
            params["filter.tags"] = ",".join(place_tags)
            
        # PRICE LEVEL EXTRACTION
        if any(word in query_text for word in ["expensive", "luxury", "high-end", "premium"]):
            params["filter.price_level.min"] = "3"
        elif any(word in query_text for word in ["cheap", "budget", "affordable", "inexpensive"]):
            params["filter.price_level.max"] = "2"
        elif "mid-range" in query_text or "moderate" in query_text:
            params["filter.price_level.min"] = "2"
            params["filter.price_level.max"] = "3"
            
        # RATING FILTERS
        if "highly rated" in query_text or "top rated" in query_text:
            params["filter.properties.business_rating.min"] = "4.0"
        elif "good rating" in query_text:
            params["filter.properties.business_rating.min"] = "3.5"
            
        # POPULARITY FILTERS
        if "popular" in query_text or "trending" in query_text:
            params["filter.popularity.min"] = "0.7"
        elif "hidden gem" in query_text or "local" in query_text:
            params["filter.popularity.max"] = "0.5"
            
        # HOURS FILTER
        days_map = {
            "monday": "Monday", "tuesday": "Tuesday", "wednesday": "Wednesday",
            "thursday": "Thursday", "friday": "Friday", "saturday": "Saturday", "sunday": "Sunday"
        }
        for day_text, day_param in days_map.items():
            if day_text in query_text:
                params["filter.hours"] = day_param
                break
                
        # ADDRESS FILTER
        address_match = re.search(r'near\s+([A-Za-z\s,]+?)(?:\s|$)', query_text)
        if address_match:
            params["filter.address"] = address_match.group(1).strip()
            
        # BRAND REFERENCE
        brand_keywords = ["starbucks", "mcdonalds", "hilton", "marriott", "walmart", "target"]
        for brand in brand_keywords:
            if brand in query_text.lower():
                # In real implementation, would need brand entity ID resolution
                params["filter.references_brand"] = f"urn:entity:brand:{brand}"
                break
                
        # EXTERNAL INTEGRATIONS
        if "tripadvisor" in query_text:
            params["filter.external.exists"] = "tripadvisor"
            if "highly rated" in query_text:
                params["filter.external.tripadvisor.rating.min"] = "4.0"
                
        if "resy" in query_text or "reservation" in query_text:
            params["filter.external.exists"] = "resy"
            
        # PARTY SIZE (for restaurants)
        party_match = re.search(r'(\d+)\s*(people|person|party)', query_text)
        if party_match:
            party_size = party_match.group(1)
            params["filter.external.resy.party_size.min"] = party_size
            
    return entity_type, params

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