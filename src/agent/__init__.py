"""
Gemini-powered autonomous astronomical agent.

This package implements the DECIDE phase of Project Sentinel's OODA loop:
- SentinelAgent: Core AI agent using Gemini 3 Flash Preview
- ContextManager: State persistence across iterations
- Data Models: Pydantic schemas for structured I/O

Usage:
    from src.agent import SentinelAgent, ContextManager
    from src.agent.models import ContextState, AgentDecision, WeatherContext
    
    # Create agent
    agent = SentinelAgent()
    
    # Test connection
    if agent.test_connection():
        print("Agent online!")
    
    # Analyze images
    decision = agent.analyze_images(
        reference=reference_image,
        current=current_image,
        diff_annotated=diff_image,
        context=context_state
    )
"""

from .models import (
    CandidateHistory,
    Candidate,
    WeatherContext,
    ContextState,
    AgentDecision,
    create_default_wait_decision,
    create_initial_context
)

from .sentinel import (
    SentinelAgent,
    create_agent
)

from .context_manager import (
    ContextManager,
    create_context_manager
)

__all__ = [
    # Models
    "CandidateHistory",
    "Candidate",
    "WeatherContext",
    "ContextState",
    "AgentDecision",
    "create_default_wait_decision",
    "create_initial_context",
    # Agent
    "SentinelAgent",
    "create_agent",
    # Context
    "ContextManager",
    "create_context_manager",
]
