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
async def analyze_cultural_moment(location: str, 
                                social_context: str = "friends", 
                                include_details: bool = True) -> str:
    """Analyze the cultural context and moment for a specific location and social situation.

    Args:
        location: City name (e.g. Mumbai, New York, Tokyo)
        social_context: Social situation (solo, couple, family, friends, business, large_group, tourists, locals)
        include_details: Whether to include detailed cultural breakdown
    """
    
    # Validate social context
    try:
        context_enum = SocialContext(social_context.lower())
    except ValueError:
        valid_contexts = [c.value for c in SocialContext]
        return f"Invalid social context '{social_context}'. Valid options: {', '.join(valid_contexts)}"
    
    print(f"🔍 Analyzing cultural moment: {location} for {social_context}")
    
    try:
        # Fetch cultural data using existing infrastructure
        cultural_data = await _fetch_cultural_landscape(location, context_enum)
        
        # Generate cultural analysis
        analysis = _generate_cultural_analysis(location, context_enum, cultural_data)
        
        # Format response
        if include_details:
            return _format_detailed_cultural_analysis(analysis)
        else:
            return _format_summary_cultural_analysis(analysis)
            
    except Exception as e:
        return f"Error analyzing cultural moment for {location}: {str(e)}"

@mcp.tool()
async def get_cultural_preferences(location: str, social_context: str = "friends") -> str:
    """Get cultural preferences and local insights for a location and social context.

    Args:
        location: City name (e.g. Mumbai, New York, Tokyo)
        social_context: Social situation (solo, couple, family, friends, business, large_group, tourists, locals)
    """
    
    try:
        context_enum = SocialContext(social_context.lower())
    except ValueError:
        return f"Invalid social context. Use: solo, couple, family, friends, business, large_group, tourists, locals"
    
    print(f"🎯 Analyzing cultural preferences: {location} for {social_context}")
    
    try:
        # Analyze preferences using existing Qloo infrastructure
        preferences = await _analyze_local_cultural_preferences(location, context_enum)
        
        return _format_cultural_preferences(location, social_context, preferences)
        
    except Exception as e:
        return f"Error getting cultural preferences for {location}: {str(e)}"

@mcp.tool()
async def get_cultural_tags(location: str, social_context: str = "friends") -> str:
    """Get cultural tags and characteristics for a location.

    Args:
        location: City name (e.g. Mumbai, New York, Tokyo)  
        social_context: Social situation (solo, couple, family, friends, business, large_group, tourists, locals)
    """
    
    try:
        context_enum = SocialContext(social_context.lower())
    except ValueError:
        return f"Invalid social context. Use: solo, couple, family, friends, business, large_group, tourists, locals"
    
    print(f"🏷️ Generating cultural tags: {location} for {social_context}")
    
    try:
        # Get cultural landscape data
        cultural_data = await _fetch_cultural_landscape(location, context_enum)
        
        # Generate tags
        tags = _generate_cultural_tags_from_data(location, context_enum, cultural_data)
        
        return _format_cultural_tags(location, social_context, tags)
        
    except Exception as e:
        return f"Error getting cultural tags for {location}: {str(e)}"

# =============================================================================
# CULTURAL CONTEXT ENGINE - HELPER FUNCTIONS
# =============================================================================

async def _fetch_cultural_landscape(location: str, social_context: SocialContext) -> dict:
    """Fetch cultural landscape data using existing Qloo API infrastructure"""
    
    cultural_data = {
        "venues": {},
        "activity_levels": {},
        "cultural_indicators": {}
    }
    
    # Use existing venue query pattern but for cultural analysis
    cultural_domains = [
        ("restaurant", "culinary"),
        ("bar", "nightlife"), 
        ("entertainment", "entertainment"),
        ("shopping", "retail"),
        ("museum", "arts"),
        ("park", "outdoor")
    ]
    
    total_venues = 0
    successful_queries = 0
    
    for venue_type, cultural_category in cultural_domains:
        try:
            # Build query using existing pattern
            params = {
                "filter.type": "urn:entity:place",
                "filter.tags": f"urn:tag:genre:place:{venue_type}",
                "filter.address": location
            }
            query_params = "&".join([f"{k}={v}" for k, v in params.items()])
            url = f"{QLOO_API_BASE}?{query_params}"
            
            # Use existing make_qloo_request function
            response = await make_qloo_request(url)
            
            if response and "error" not in response:
                results = response.get('results', {})
                entities = results.get('entities', []) if isinstance(results, dict) else results
                
                venue_count = len(entities)
                activity_score = min(venue_count / 20.0, 1.0)  # Normalize
                
                cultural_data["venues"][cultural_category] = entities[:5]  # Sample venues
                cultural_data["activity_levels"][cultural_category] = activity_score
                
                total_venues += venue_count
                successful_queries += 1
                
        except Exception as e:
            print(f"Warning: Could not fetch {venue_type} data: {e}")
            cultural_data["activity_levels"][cultural_category] = 0.3  # Default
    
    # Calculate overall cultural activity
    cultural_data["overall_activity"] = sum(cultural_data["activity_levels"].values()) / max(len(cultural_data["activity_levels"]), 1)
    cultural_data["total_venues"] = total_venues
    cultural_data["successful_queries"] = successful_queries
    
    return cultural_data

def _generate_cultural_analysis(location: str, social_context: SocialContext, cultural_data: dict) -> dict:
    """Generate cultural analysis from the fetched data"""
    
    # Calculate cultural metrics
    overall_activity = cultural_data.get("overall_activity", 0.5)
    total_venues = cultural_data.get("total_venues", 0)
    
    # Determine cultural intensity based on activity and context
    intensity_adjustments = {
        SocialContext.FRIENDS: 0.2,
        SocialContext.LARGE_GROUP: 0.15,
        SocialContext.COUPLE: 0.0,
        SocialContext.FAMILY: -0.1,
        SocialContext.BUSINESS: -0.05,
        SocialContext.SOLO: -0.15
    }
    
    base_intensity = overall_activity
    context_adjustment = intensity_adjustments.get(social_context, 0.0)
    cultural_intensity = max(0.0, min(1.0, base_intensity + context_adjustment))
    
    # Generate cultural characteristics
    characteristics = []
    activity_levels = cultural_data.get("activity_levels", {})
    
    # Determine dominant cultural aspects
    if activity_levels.get("culinary", 0) > 0.6:
        characteristics.append("food-focused")
    if activity_levels.get("nightlife", 0) > 0.6:
        characteristics.append("vibrant nightlife")
    if activity_levels.get("arts", 0) > 0.6:
        characteristics.append("arts-rich")
    if activity_levels.get("entertainment", 0) > 0.6:
        characteristics.append("entertainment hub")
    
    # Overall activity level descriptors
    if cultural_intensity > 0.7:
        characteristics.append("high-energy")
    elif cultural_intensity < 0.3:
        characteristics.append("relaxed")
    else:
        characteristics.append("balanced")
    
    # Social context specific insights
    context_insights = {
        SocialContext.FRIENDS: "Great for group activities and socializing",
        SocialContext.COUPLE: "Perfect for intimate and romantic experiences",
        SocialContext.FAMILY: "Family-friendly options available",
        SocialContext.BUSINESS: "Professional and networking opportunities",
        SocialContext.SOLO: "Ideal for personal exploration and discovery",
        SocialContext.TOURISTS: "Tourist-friendly with cultural attractions",
        SocialContext.LOCALS: "Authentic local experiences",
        SocialContext.LARGE_GROUP: "Suitable for large group gatherings"
    }
    
    return {
        "location": location,
        "social_context": social_context.value,
        "cultural_intensity": cultural_intensity,
        "total_venues": total_venues,
        "characteristics": characteristics,
        "activity_breakdown": activity_levels,
        "context_insight": context_insights.get(social_context, ""),
        "confidence": min(cultural_data.get("successful_queries", 0) / 6.0, 1.0)
    }

def _format_detailed_cultural_analysis(analysis: dict) -> str:
    """Format detailed cultural analysis for output"""
    
    location = analysis["location"]
    context = analysis["social_context"] 
    intensity = analysis["cultural_intensity"]
    characteristics = analysis["characteristics"]
    activity_breakdown = analysis["activity_breakdown"]
    
    result = f"🎭 **Cultural Analysis: {location} for {context}**\n\n"
    
    # Cultural intensity
    intensity_emoji = "🔥" if intensity > 0.7 else "⭐" if intensity > 0.4 else "✨"
    result += f"{intensity_emoji} **Cultural Intensity:** {intensity:.2f}/1.0\n"
    
    # Key characteristics
    if characteristics:
        result += f"🏷️ **Cultural Characteristics:** {', '.join(characteristics)}\n"
    
    # Activity breakdown
    result += f"\n📊 **Activity Breakdown:**\n"
    for category, level in activity_breakdown.items():
        level_emoji = "🔥" if level > 0.7 else "📍" if level > 0.4 else "💤"
        result += f"   {level_emoji} {category.title()}: {level:.2f}\n"
    
    # Context insight
    if analysis.get("context_insight"):
        result += f"\n💡 **For {context}:** {analysis['context_insight']}\n"
    
    # Confidence level
    confidence = analysis.get("confidence", 0.0)
    conf_emoji = "🔒" if confidence > 0.8 else "🔓" if confidence > 0.5 else "⚠️"
    result += f"\n{conf_emoji} **Analysis Confidence:** {confidence:.2f}\n"
    
    return result

def _format_summary_cultural_analysis(analysis: dict) -> str:
    """Format summary cultural analysis for output"""
    
    location = analysis["location"]
    context = analysis["social_context"]
    intensity = analysis["cultural_intensity"]
    characteristics = analysis["characteristics"][:3]  # Top 3
    
    intensity_desc = "high-energy" if intensity > 0.7 else "relaxed" if intensity < 0.3 else "balanced"
    
    result = f"🎯 {location} for {context}: {intensity_desc} cultural scene"
    
    if characteristics:
        result += f" with {', '.join(characteristics)} characteristics"
    
    result += f" (intensity: {intensity:.2f})"
    
    return result

async def _analyze_local_cultural_preferences(location: str, social_context: SocialContext) -> dict:
    """Analyze local cultural preferences for the given context"""
    
    # Get cultural landscape data
    cultural_data = await _fetch_cultural_landscape(location, social_context)
    activity_levels = cultural_data.get("activity_levels", {})
    
    # Context-specific preference adjustments
    preference_boosts = {
        SocialContext.FRIENDS: {"nightlife": 0.3, "entertainment": 0.2},
        SocialContext.COUPLE: {"culinary": 0.3, "arts": 0.2},
        SocialContext.FAMILY: {"outdoor": 0.3, "entertainment": 0.2},
        SocialContext.BUSINESS: {"culinary": 0.2, "retail": 0.1},
        SocialContext.SOLO: {"arts": 0.3, "outdoor": 0.2},
        SocialContext.TOURISTS: {"arts": 0.3, "entertainment": 0.2},
        SocialContext.LOCALS: {"culinary": 0.2, "nightlife": 0.1}
    }
    
    # Start with base activity levels
    preferences = dict(activity_levels)
    
    # Apply context-specific boosts
    if social_context in preference_boosts:
        for category, boost in preference_boosts[social_context].items():
            if category in preferences:
                preferences[category] = min(preferences[category] + boost, 1.0)
            else:
                preferences[category] = boost
    
    return preferences

def _format_cultural_preferences(location: str, social_context: str, preferences: dict) -> str:
    """Format cultural preferences for output"""
    
    result = f"🎯 **Cultural Preferences: {location} for {social_context}**\n\n"
    
    # Sort preferences by score
    sorted_prefs = sorted(preferences.items(), key=lambda x: x[1], reverse=True)
    
    for category, score in sorted_prefs:
        emoji = "🎪" if score > 0.7 else "🎨" if score > 0.5 else "📝"
        result += f"{emoji} **{category.title()}:** {score:.2f}\n"
    
    # Add recommendation
    if sorted_prefs:
        top_category = sorted_prefs[0][0]
        result += f"\n💡 **Recommendation:** Focus on {top_category} experiences for this context"
    
    return result

def _generate_cultural_tags_from_data(location: str, social_context: SocialContext, cultural_data: dict) -> list:
    """Generate cultural tags from analyzed data"""
    
    tags = []
    activity_levels = cultural_data.get("activity_levels", {})
    overall_activity = cultural_data.get("overall_activity", 0.5)
    
    # Activity-based tags
    if overall_activity > 0.7:
        tags.append("high-activity")
    elif overall_activity < 0.3:
        tags.append("relaxed")
    else:
        tags.append("moderate-activity")
    
    # Domain-specific tags
    for domain, level in activity_levels.items():
        if level > 0.6:
            tags.append(f"vibrant-{domain}")
        elif level > 0.4:
            tags.append(f"good-{domain}")
    
    # Social context tags
    context_tags = {
        SocialContext.FRIENDS: ["social", "group-friendly"],
        SocialContext.COUPLE: ["romantic", "intimate"],
        SocialContext.FAMILY: ["family-friendly", "accessible"],
        SocialContext.BUSINESS: ["professional", "networking"],
        SocialContext.SOLO: ["solo-friendly", "discovery"],
        SocialContext.TOURISTS: ["tourist-friendly", "cultural"],
        SocialContext.LOCALS: ["authentic", "local"],
        SocialContext.LARGE_GROUP: ["group-suitable", "spacious"]
    }
    
    if social_context in context_tags:
        tags.extend(context_tags[social_context])
    
    # Location-specific cultural tags (basic examples)
    location_lower = location.lower()
    if any(city in location_lower for city in ["mumbai", "delhi", "bangalore"]):
        tags.extend(["bollywood-influenced", "diverse-cuisine", "vibrant-culture"])
    elif any(city in location_lower for city in ["tokyo", "kyoto", "osaka"]):
        tags.extend(["traditional-modern-blend", "tech-forward", "respectful-culture"])
    elif any(city in location_lower for city in ["new york", "london", "paris"]):
        tags.extend(["cosmopolitan", "arts-focused", "international"])
    
    return tags[:10]  # Return top 10 most relevant tags

def _format_cultural_tags(location: str, social_context: str, tags: list) -> str:
    """Format cultural tags for output"""
    
    result = f"🏷️ **Cultural Tags: {location} for {social_context}**\n\n"
    
    if tags:
        for i, tag in enumerate(tags, 1):
            result += f"{i}. {tag}\n"
        
        # Group tags by category
        activity_tags = [tag for tag in tags if "activity" in tag]
        venue_tags = [tag for tag in tags if any(word in tag for word in ["vibrant", "good"])]
        context_tags = [tag for tag in tags if tag not in activity_tags and tag not in venue_tags]
        
        if activity_tags:
            result += f"\n🎯 **Activity Level:** {', '.join(activity_tags)}\n"
        if venue_tags:
            result += f"🏢 **Venue Strengths:** {', '.join(venue_tags)}\n"
        if context_tags:
            result += f"👥 **Context Characteristics:** {', '.join(context_tags)}\n"
    else:
        result += "No specific cultural tags identified.\n"
    
    return result